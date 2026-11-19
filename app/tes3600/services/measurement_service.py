import threading
import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from app.tes3600.decoder import TES3600Decoder
from app.tes3600.services.connection_service import ConnectionService

from app.tes3600.network.protocol import parse_message
from app.tes3600.network.tcp_client import TCPClient
from app.device_manager.device import Device


class MeasurementService(QThread):
    """Adquiere y decodifica mediciones del TES3600."""

    measurements_received = Signal(dict)
    valid_frame_received = Signal(object)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    log_message = Signal(str)

    POLL_INTERVAL = 0.022
    REQUEST_INTERVAL = 0.500
    READY_DELAY = 0.050
    FRAME_PAUSE = 0.005
    SIGNAL_TIMEOUT = 1.5

    def __init__(self, port: str, parent=None):
        super().__init__(parent)

        self.connection = ConnectionService(port)
        self.decoder = TES3600Decoder()
        self._stop_event = threading.Event()

    def stop(self):
        """Solicita la detención del servicio."""
        self._stop_event.set()

    def run(self):
        try:
            self.connection.connect()
            self.log_message.emit(
                f"Conectado al TES3600 por {self.connection.port}"
            )
            self.status_changed.emit("Sin datos")

            # Inicialización del protocolo.
            self.connection.write(b"\x45")
            self.log_message.emit("PC -> TES: 45")

            listo = False
            inicio_ready = None
            ultima_trama_valida = None

            proximo_poll = time.perf_counter()
            proxima_solicitud = None

            buffer = bytearray()
            ultimo_byte = None

            while not self._stop_event.is_set():
                ahora = time.perf_counter()

                # Polling: 77 00.
                if ahora >= proximo_poll:
                    self.connection.write(b"\x77\x00")
                    proximo_poll = ahora + self.POLL_INTERVAL

                # Solicitudes de medición: 20.
                if listo and inicio_ready is not None:
                    if (
                        ahora - inicio_ready >= self.READY_DELAY
                        and proxima_solicitud is None
                    ):
                        proxima_solicitud = ahora

                    if (
                        proxima_solicitud is not None
                        and ahora >= proxima_solicitud
                    ):
                        self.connection.write(b"\x20")
                        proxima_solicitud = (
                            ahora + self.REQUEST_INTERVAL
                        )

                # Leer bytes disponibles.
                data = self.connection.read(
                    max(1, self.connection.available_bytes)
                )
                ahora = time.perf_counter()

                if data:
                    # Una pausa mayor a 5 ms separa los bloques.
                    if (
                        ultimo_byte is not None
                        and ahora - ultimo_byte > self.FRAME_PAUSE
                        and buffer
                    ):
                        bloque = bytes(buffer)
                        buffer.clear()

                        resultado = self._process_block(bloque)

                        if resultado == "ready" and not listo:
                            listo = True
                            inicio_ready = time.perf_counter()
                            self.log_message.emit(
                                "TES listo (77 recibido)"
                            )

                        elif resultado == "valid":
                            ultima_trama_valida = time.perf_counter()

                    buffer.extend(data)
                    ultimo_byte = ahora

                elif (
                    ultimo_byte is not None
                    and buffer
                    and ahora - ultimo_byte > self.FRAME_PAUSE
                ):
                    bloque = bytes(buffer)
                    buffer.clear()
                    ultimo_byte = None

                    resultado = self._process_block(bloque)

                    if resultado == "ready" and not listo:
                        listo = True
                        inicio_ready = time.perf_counter()
                        self.log_message.emit(
                            "TES listo (77 recibido)"
                        )

                    elif resultado == "valid":
                        ultima_trama_valida = time.perf_counter()

                # Detectar pérdida de señal.
                if (
                    ultima_trama_valida is not None
                    and ahora - ultima_trama_valida > self.SIGNAL_TIMEOUT
                ):
                    self.status_changed.emit("Sin señal")
                    ultima_trama_valida = None

        except Exception as exc:
            self.error_occurred.emit(str(exc))
            self.status_changed.emit("Sin señal")

        finally:
            self.connection.close()
            self.log_message.emit("Conexión serie cerrada")

    def _available_bytes(self) -> int:
        """Cantidad de bytes que ya están disponibles."""
        serial_port = self.connection._serial

        if serial_port is None or not serial_port.is_open:
            return 1

        return max(1, serial_port.in_waiting)

    def _process_block(self, block: bytes) -> str | None:
        """Procesa un bloque y devuelve su tipo si se reconoce."""

        if block == b"\x77":
            return "ready"

        measurements = self.decoder.decode(block)

        if measurements is None:
            self.log_message.emit(
                f"Bloque ignorado ({len(block)} bytes)"
            )
            return None

        timestamp = datetime.now()

        self.measurements_received.emit(measurements)
        self.valid_frame_received.emit(timestamp)
        self.status_changed.emit("Recibiendo")

        return "valid"
    


class TCPMeasurementService(QThread):
    """Recibe, interpreta y decodifica mediciones desde un servidor TCP."""

    measurements_received = Signal(dict)
    valid_frame_received = Signal(object)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    log_message = Signal(str)
    connected = Signal()

    SIGNAL_TIMEOUT = 1.5
    READ_TIMEOUT = 0.2

    def __init__(
        self,
        device: Device,
        parent=None,
        signal_timeout: float = SIGNAL_TIMEOUT,
        read_timeout: float = READ_TIMEOUT,
    ):
        super().__init__(parent)

        self.device = device
        self.signal_timeout = signal_timeout
        self.read_timeout = read_timeout
        self.current_status = "Sin datos"
        self._stop_event = threading.Event()
        self.client = None

    def stop(self):
        """Solicita la detención del hilo."""
        self._stop_event.set()

    def run(self):
        try:
            if self._stop_event.is_set():
                return

            # La conexión se abre dentro del hilo, no en la interfaz.
            self.client = TCPClient(
                self.device,
                stop_event=self._stop_event,
            )

            self.log_message.emit(
                f"Conectado al servidor TCP "
                f"{self.device.host}:{self.device.port}"
            )
            self.connected.emit()
            self.current_status = "Sin datos"
            self.status_changed.emit("Sin datos")

            decoder = TES3600Decoder()
            ultima_trama_valida = None

            while not self._stop_event.is_set():
                try:
                    data = self.client.receive_message(timeout=self.read_timeout)
                except (ConnectionError, OSError) as exc:
                    if not self._stop_event.is_set():
                        self.error_occurred.emit(str(exc))
                        if self.current_status != "Sin señal":
                            self.current_status = "Sin señal"
                            self.status_changed.emit("Sin señal")
                    break

                if self._stop_event.is_set():
                    break

                ahora = time.perf_counter()

                if data is not None:
                    try:
                        message = parse_message(data)
                        measurements = decoder.decode(message.frame)

                        if measurements is None:
                            self.log_message.emit(
                                "Se recibió una trama TES3600 no válida."
                            )
                        else:
                            # Los nombres de la interfaz difieren de los del decodificador.
                            # Se conservan los valores originales, sin cambiar sus escalas.
                            ui_measurements = dict(measurements)

                            aliases = {
                                "P1": "kW1",
                                "Q1": "kVAR1",
                                "S1": "kVA1",
                            }

                            for source, destination in aliases.items():
                                if source in ui_measurements:
                                    ui_measurements[destination] = (
                                        ui_measurements.pop(source)
                                    )

                            if message.timestamp is not None:
                                timestamp = message.timestamp
                            else:
                                timestamp = datetime.now().replace(
                                    hour=message.hour,
                                    minute=message.minute,
                                    second=message.second,
                                    microsecond=message.millisecond * 1000,
                                )

                            ultima_trama_valida = ahora

                            if self.current_status != "Recibiendo":
                                self.current_status = "Recibiendo"
                                self.status_changed.emit("Recibiendo")

                            self.measurements_received.emit(ui_measurements)
                            self.valid_frame_received.emit(timestamp)

                    except ValueError as exc:
                        # Trama con delimitadores, longitud o marca temporal inválida.
                        # Se descarta la medición sin cerrar el socket ni actualizar
                        # el instante de la última trama válida.
                        self.log_message.emit(
                            f"Trama inválida descartada: {exc}"
                        )
                    except Exception as exc:
                        # Error inesperado durante la decodificación.
                        # Se descarta la medición sin cerrar el socket.
                        self.log_message.emit(
                            f"Error al decodificar medición: {exc}"
                        )

                # Detección de pérdida de señal tras agotar el tiempo de espera
                if (
                    ultima_trama_valida is not None
                    and (ahora - ultima_trama_valida > self.signal_timeout)
                ):
                    if self.current_status != "Sin señal":
                        self.current_status = "Sin señal"
                        self.status_changed.emit("Sin señal")
                    ultima_trama_valida = None

        except InterruptedError:
            pass

        except Exception as exc:
            if not self._stop_event.is_set():
                self.error_occurred.emit(str(exc))
                self.current_status = "Sin señal"
                self.status_changed.emit("Sin señal")

        finally:
            if self.client is not None:
                self.client.close()
                self.client = None

            self.log_message.emit("Recepción TCP finalizada")
