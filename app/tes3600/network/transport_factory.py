import socket
import serial

from app.device_manager.device import Device


class TCPTransport:
    def __init__(self, host: str, port: int):
        self.socket = socket.create_connection(
            (host, port),
            timeout=3,
        )
        self.socket.settimeout(0.1)

    @property
    def is_connected(self) -> bool:
        return self.socket is not None

    def read(self, size: int = 1) -> bytes:
        return self.socket.recv(size)

    def write(self, data: bytes) -> None:
        self.socket.sendall(data)

    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None


class SerialTransport:
    def __init__(self, port: str):
        self.serial = serial.Serial(
            port=port,
            baudrate=19200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=1,
            rtscts=False,
            dsrdtr=False,
        )

        self.serial.dtr = True
        self.serial.rts = False

    @property
    def is_connected(self) -> bool:
        return self.serial.is_open

    def read(self, size: int = 1) -> bytes:
        return self.serial.read(size)

    def write(self, data: bytes) -> None:
        self.serial.write(data)
        self.serial.flush()

    def close(self) -> None:
        if self.serial.is_open:
            self.serial.close()


def open_device_connection(device: Device):
    if device.connection_type == "tcp":
        return TCPTransport(device.host, device.port)

    if device.connection_type == "serial":
        return SerialTransport(device.serial_port)

    raise ValueError(
        f"Tipo de conexión desconocido: {device.connection_type}"
    )
