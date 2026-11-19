"""Servicio de descarga y decodificación asíncrona de mediciones históricas."""

from __future__ import annotations

import logging
import math
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from app.tes3600.decoder import TES3600Decoder
from app.tes3600.network.history_client import HistoryTCPClient

logger = logging.getLogger("PowerAnalyzer.HistoryService")

# Tolerancia fija para asociar una muestra real con cada instante objetivo.
# Con el intervalo mínimo de 500 ms, las ventanas no se superponen.
SAMPLE_TOLERANCE_MS = 250


def estimate_sample_interval(samples: list[list[Any]]) -> float:
    """Estima el intervalo predominante entre las marcas temporales seleccionadas."""
    parsed: list[datetime] = []
    for sample in samples[:30]:
        if not sample or not sample[0]:
            continue
        val = sample[0]
        if isinstance(val, datetime):
            parsed.append(val)
        elif isinstance(val, str):
            try:
                parsed.append(datetime.fromisoformat(val))
            except ValueError:
                pass

    differences = []
    for prev_dt, curr_dt in zip(parsed, parsed[1:]):
        delta = (curr_dt - prev_dt).total_seconds()
        if delta > 0 and math.isfinite(delta):
            differences.append(round(delta, 3))

    if not differences:
        return 0.5

    counts = Counter(differences)
    highest_count = max(counts.values())
    return float(min(val for val, count in counts.items() if count == highest_count))


def select_samples_by_interval(
    records: list[tuple[int, list[Any]]],
    interval_ms: int,
    tolerance_ms: int = SAMPLE_TOLERANCE_MS,
) -> list[list[Any]]:
    """Selecciona la muestra más cercana a cada objetivo relativo al primer registro.

    El primer registro válido siempre se conserva y define T0. Los objetivos
    posteriores son T0 + n * interval_ms; nunca se recalculan desde la muestra
    seleccionada anterior, evitando acumular desviaciones.
    """
    if not records:
        return []
    if interval_ms < 500 or interval_ms > 3_600_000:
        raise ValueError("El intervalo de muestreo debe estar entre 500 ms y 1 hora.")
    if tolerance_ms < 0 or tolerance_ms * 2 >= interval_ms:
        raise ValueError("La tolerancia debe ser positiva y menor que la mitad del intervalo.")

    # La secuencia del servidor debe ser cronológica para que el filtrado sea determinista.
    previous_timestamp = records[0][0]
    for timestamp_ms, _ in records[1:]:
        if timestamp_ms < previous_timestamp:
            raise ValueError("El servidor entregó mediciones fuera de orden temporal.")
        previous_timestamp = timestamp_ms

    selected = [records[0][1]]
    target_ms = records[0][0] + interval_ms
    candidate: tuple[int, list[Any]] | None = None

    for timestamp_ms, row in records[1:]:
        # Al superar el límite superior, se cierra la ventana actual.
        while timestamp_ms > target_ms + tolerance_ms:
            if candidate is not None:
                selected.append(candidate[1])
                candidate = None
            target_ms += interval_ms

        lower_bound = target_ms - tolerance_ms
        upper_bound = target_ms + tolerance_ms
        if lower_bound <= timestamp_ms <= upper_bound:
            if candidate is None:
                candidate = (timestamp_ms, row)
            else:
                current_distance = abs(candidate[0] - target_ms)
                new_distance = abs(timestamp_ms - target_ms)
                # En caso de empate se conserva la primera muestra recibida.
                if new_distance < current_distance:
                    candidate = (timestamp_ms, row)

    if candidate is not None:
        selected.append(candidate[1])

    return selected


class HistoryDownloadWorker(QThread):
    """Hilo secundario para ejecutar la descarga histórica sin bloquear la interfaz gráfica."""

    status_updated = Signal(str)
    records_count_updated = Signal(int)
    finished_successfully = Signal(dict)
    error_occurred = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        host: str,
        port: int,
        request_mode: str,  # "predefined" o "custom"
        name: str,
        destination_mode: str,  # "internal" o "local_file"
        period_code: int | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        sample_interval_ms: int = 500,
        export_path: Path | None = None,
        export_extension: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.host = host
        self.port = port
        self.request_mode = request_mode
        self.name = name.strip()
        self.destination_mode = destination_mode
        self.period_code = period_code
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.sample_interval_ms = sample_interval_ms
        self.export_path = export_path
        self.export_extension = export_extension

        self._stop_event = threading.Event()
        self._client: HistoryTCPClient | None = None

    def cancel(self) -> None:
        """Solicita la detención inmediata de la descarga."""
        self._stop_event.set()
        if self._client is not None:
            self._client.close()

    def run(self) -> None:
        """Descarga todos los registros y aplica el filtrado temporal en el cliente."""
        decoder = TES3600Decoder()
        raw_records: list[tuple[int, list[Any]]] = []
        headers: list[str] = []

        aliases = {
            "P1": "kW1",
            "Q1": "kVAR1",
            "S1": "kVA1",
        }

        try:
            if not 500 <= self.sample_interval_ms <= 3_600_000:
                raise ValueError("El intervalo debe estar entre 500 ms y 1 hora.")

            self.status_updated.emit(f"Conectando al servidor {self.host}:{self.port}...")
            self._client = HistoryTCPClient(
                host=self.host,
                port=self.port,
                timeout=12.0,
                stop_event=self._stop_event,
            )
            self._client.connect()

            if self._stop_event.is_set():
                raise InterruptedError("Operación cancelada.")

            if self.request_mode == "predefined":
                if self.period_code is None:
                    raise ValueError("Falta el código de período predefinido.")
                self._client.send_predefined_request(self.period_code)
            elif self.request_mode == "custom":
                if self.start_ms is None or self.end_ms is None:
                    raise ValueError("Faltan las marcas temporales del período personalizado.")
                self._client.send_custom_request(self.start_ms, self.end_ms)
            else:
                raise ValueError(f"Modo de solicitud desconocido: {self.request_mode}")

            self.status_updated.emit("Descargando mediciones originales...")
            received_count = 0

            for timestamp_ms, frame in self._client.iter_records():
                if self._stop_event.is_set():
                    raise InterruptedError("Operación cancelada.")

                measurements = decoder.decode(frame)
                if measurements is None:
                    continue

                ui_measurements = dict(measurements)
                for src, dst in aliases.items():
                    if src in ui_measurements:
                        ui_measurements[dst] = ui_measurements.pop(src)

                if not headers:
                    headers = list(ui_measurements.keys())

                dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
                iso_timestamp = dt.isoformat(sep=" ", timespec="milliseconds")
                row = [iso_timestamp] + [ui_measurements.get(h, "") for h in headers]
                raw_records.append((timestamp_ms, row))

                received_count += 1
                if received_count % 25 == 0 or received_count == 1:
                    self.records_count_updated.emit(received_count)
                    self.status_updated.emit(
                        f"Descargando mediciones: {received_count:,} recibidas..."
                    )

            self.records_count_updated.emit(received_count)

            if received_count == 0:
                self.status_updated.emit("La consulta finalizó sin registros disponibles.")
                self.finished_successfully.emit({
                    "name": self.name,
                    "started_at": datetime.now(),
                    "duration_seconds": 1,
                    "sample_interval_seconds": self.sample_interval_ms / 1000.0,
                    "headers": headers,
                    "samples": [],
                    "destination_mode": self.destination_mode,
                    "export_path": self.export_path,
                    "export_extension": self.export_extension,
                    "count": 0,
                    "received_count": 0,
                })
                return

            self.status_updated.emit("Aplicando intervalo de muestreo...")
            samples = select_samples_by_interval(raw_records, self.sample_interval_ms)

            first_selected_ms = raw_records[0][0]
            # La última muestra seleccionada determina el final efectivo del registro.
            last_selected_iso = datetime.fromisoformat(samples[-1][0])
            started_at = datetime.fromtimestamp(first_selected_ms / 1000.0)
            ended_at = last_selected_iso
            duration_seconds = max(1, int((ended_at - started_at).total_seconds()))
            interval = (
                estimate_sample_interval(samples)
                if len(samples) > 1
                else self.sample_interval_ms / 1000.0
            )

            if self.destination_mode == "internal":
                self.status_updated.emit("Creando registro en Power Analyzer...")
            else:
                self.status_updated.emit("Exportando archivo local...")

            selected_count = len(samples)
            self.status_updated.emit(
                f"Descarga finalizada: {selected_count:,} conservadas de {received_count:,} recibidas."
            )

            self.finished_successfully.emit({
                "name": self.name,
                "started_at": started_at,
                "duration_seconds": duration_seconds,
                "sample_interval_seconds": interval,
                "requested_sample_interval_ms": self.sample_interval_ms,
                "headers": headers,
                "samples": samples,
                "destination_mode": self.destination_mode,
                "export_path": self.export_path,
                "export_extension": self.export_extension,
                "count": selected_count,
                "received_count": received_count,
            })

        except InterruptedError:
            self.status_updated.emit("Descarga cancelada.")
            self.cancelled.emit()
        except Exception as exc:
            logger.exception("Error durante la descarga histórica.")
            self.status_updated.emit(f"Error: {exc}")
            self.error_occurred.emit(str(exc))
        finally:
            if self._client is not None:
                self._client.close()
                self._client = None
