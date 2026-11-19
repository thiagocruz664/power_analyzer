"""Cliente TCP para consulta y descarga de mediciones históricas del analizador TES3600."""

from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Generator

# Protocolo del servidor histórico
HISTORY_PORT_DEFAULT = 9001
HEADER_SIZE = 4
TIMESTAMP_SIZE = 8
FRAME_SIZE = 61
RECORD_PAYLOAD_SIZE = TIMESTAMP_SIZE + FRAME_SIZE  # 69 bytes
TOTAL_RECORD_SIZE = HEADER_SIZE + RECORD_PAYLOAD_SIZE  # 73 bytes

FRAME_START = 0x02
FRAME_END = 0x03

PREDEFINED_PERIOD_CODES = {
    "1h": 0x01,
    "3h": 0x02,
    "6h": 0x03,
    "12h": 0x04,
    "24h": 0x05,
    "3d": 0x06,
    "7d": 0x07,
    "15d": 0x08,
    "30d": 0x09,
}
CUSTOM_PERIOD_CODE = 0x0F


class HistoryTCPClient:
    """Cliente para la conexión y descarga de registros históricos desde el puerto 9001."""

    def __init__(
        self,
        host: str,
        port: int = HISTORY_PORT_DEFAULT,
        timeout: float = 10.0,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.stop_event = stop_event or threading.Event()
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        """Establece la conexión TCP con el servidor histórico."""
        if self._socket is not None:
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)

        try:
            sock.connect((self.host, self.port))
            self._socket = sock
        except Exception:
            sock.close()
            raise

    def send_predefined_request(self, code: int) -> None:
        """Envía el código de período predefinido (0x01 a 0x09)."""
        if code not in range(0x01, 0x0A):
            raise ValueError(f"Código de período predefinido no válido: 0x{code:02X}")

        self._send_all(bytes([code]))

    def send_custom_request(self, start_ms: int, end_ms: int) -> None:
        """Envía la solicitud de período personalizado (0x0F + start_ms + end_ms).
        
        Tanto start_ms como end_ms deben ser Unix timestamps en milisegundos (enteros).
        """
        if start_ms > end_ms:
            raise ValueError("El timestamp inicial no puede superar al final.")

        payload = struct.pack("!BQQ", CUSTOM_PERIOD_CODE, int(start_ms), int(end_ms))
        self._send_all(payload)

    def _send_all(self, data: bytes) -> None:
        """Transmite la totalidad de los bytes asegurando que el socket esté activo."""
        if self._socket is None:
            raise ConnectionError("No hay conexión activa con el servidor histórico.")

        self._socket.sendall(data)

    def _recv_exact(self, size: int) -> bytes:
        """Recibe exactamente la cantidad de bytes requerida, manejando fragmentación TCP."""
        if self._socket is None:
            raise ConnectionError("No hay conexión activa con el servidor histórico.")

        data = bytearray()
        while len(data) < size:
            if self.stop_event.is_set():
                raise InterruptedError("Descarga cancelada por el usuario.")

            try:
                chunk = self._socket.recv(size - len(data))
            except socket.timeout:
                if self.stop_event.is_set():
                    raise InterruptedError("Descarga cancelada por el usuario.")
                continue

            if not chunk:
                raise ConnectionError(
                    "El servidor cerró la conexión prematuramente antes de completar los datos."
                )

            data.extend(chunk)

        return bytes(data)

    def iter_records(self) -> Generator[tuple[int, bytes], None, None]:
        """Itera y produce tuplas (timestamp_ms, frame) recibidas del servidor.
        
        Finaliza normalmente cuando el servidor transmite cuatro bytes con valor cero.
        Lanza excepción si la longitud del registro no coincide con el formato definitivo (69).
        """
        while not self.stop_event.is_set():
            # 1. Leer longitud del registro (4 bytes, big-endian)
            header = self._recv_exact(HEADER_SIZE)
            payload_len = struct.unpack("!I", header)[0]

            # 2. Terminador de descarga (00 00 00 00)
            if payload_len == 0:
                return

            # 3. Validación de formato definitivo unificado
            if payload_len != RECORD_PAYLOAD_SIZE:
                raise ValueError(
                    f"Longitud de registro inesperada: se esperaban {RECORD_PAYLOAD_SIZE} bytes, "
                    f"se recibieron {payload_len}."
                )

            # 4. Leer contenido del registro (69 bytes: 8B timestamp + 61B trama)
            payload = self._recv_exact(RECORD_PAYLOAD_SIZE)
            timestamp_ms = struct.unpack("!Q", payload[:TIMESTAMP_SIZE])[0]
            frame = payload[TIMESTAMP_SIZE:]

            if len(frame) != FRAME_SIZE:
                raise ValueError(
                    f"Longitud de trama incorrecta: se esperaban {FRAME_SIZE} bytes, "
                    f"se recibieron {len(frame)}."
                )

            if frame[0] != FRAME_START or frame[-1] != FRAME_END:
                raise ValueError("Delimitadores de trama TES3600 inválidos en registro histórico.")

            yield timestamp_ms, frame

        raise InterruptedError("Descarga cancelada por el usuario.")

    def close(self) -> None:
        """Cierra el socket y libera recursos."""
        self.stop_event.set()
        sock = self._socket
        self._socket = None

        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
