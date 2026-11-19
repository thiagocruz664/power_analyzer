import socket
import struct
import threading
import time

from app.device_manager.device import Device
from app.tes3600.network.transport_factory import TCPTransport


HEADER_SIZE = 4
MAX_MESSAGE_SIZE = 1024 * 1024


class TCPClient:
    """Cliente TCP para recibir mensajes del servidor TES3600."""

    def __init__(
        self,
        device: Device,
        stop_event: threading.Event | None = None,
    ):
        if device.connection_type != "tcp":
            raise ValueError(
                "El dispositivo seleccionado no utiliza TCP."
            )

        self.device = device
        self.stop_event = stop_event or threading.Event()
        self.transport = TCPTransport(device.host, device.port)
        self._buffer = bytearray()

    def receive_message(self, timeout: float | None = None) -> bytes | None:
        """
        Recibe un mensaje completo utilizando el encabezado de longitud.

        Si se especifica timeout y transcurre sin completarse una trama, retorna None.
        Si la conexión se cierra, lanza ConnectionError.
        Si se solicita la detención, lanza InterruptedError.
        """
        deadline = (time.monotonic() + timeout) if timeout is not None else None

        while not self.stop_event.is_set():
            # Si ya tenemos al menos el encabezado en el buffer
            if len(self._buffer) >= HEADER_SIZE:
                message_size = struct.unpack("!I", self._buffer[:HEADER_SIZE])[0]

                if message_size > MAX_MESSAGE_SIZE:
                    raise ValueError(
                        f"Longitud de mensaje inválida: {message_size} bytes."
                    )

                total_size = HEADER_SIZE + message_size
                if len(self._buffer) >= total_size:
                    # Mensaje completo disponible
                    payload = bytes(self._buffer[HEADER_SIZE:total_size])
                    del self._buffer[:total_size]
                    return payload

            # Si se agotó el tiempo de espera para recibir más datos
            if deadline is not None and time.monotonic() >= deadline:
                return None

            try:
                # Leer datos disponibles del socket
                chunk = self.transport.read(4096)
            except (TimeoutError, socket.timeout):
                continue

            if not chunk:
                raise ConnectionError(
                    "El servidor TCP cerró la conexión."
                )

            self._buffer.extend(chunk)

        raise InterruptedError("Recepción TCP cancelada.")

    def close(self) -> None:
        """Cierra la conexión TCP."""
        self.stop_event.set()
        self.transport.close()
