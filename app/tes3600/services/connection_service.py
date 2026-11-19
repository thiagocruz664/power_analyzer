import serial


class ConnectionService:
    """Gestiona la conexión serie con el TES3600."""

    BAUDRATE = 19200

    def __init__(self, port: str):
        self.port = port
        self._serial = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def available_bytes(self) -> int:
        """Cantidad de bytes pendientes de lectura."""
        if not self.is_connected:
            return 0

        return self._serial.in_waiting
    
    def connect(self) -> None:
        """Abre el puerto serie con la configuración conocida."""
        if self.is_connected:
            return

        connection = serial.Serial(
            port=self.port,
            baudrate=self.BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.005,
            write_timeout=1,
            rtscts=False,
            dsrdtr=False,
        )

        try:
            connection.dtr = True
            connection.rts = False
        except Exception:
            connection.close()
            raise

        self._serial = connection

    def read(self, size: int = 1) -> bytes:
        """Lee bytes disponibles del puerto."""
        if not self.is_connected:
            raise ConnectionError("El TES3600 no está conectado.")

        return self._serial.read(size)

    def write(self, data: bytes) -> None:
        """Envía bytes al TES3600."""
        if not self.is_connected:
            raise ConnectionError("El TES3600 no está conectado.")

        self._serial.write(data)
        self._serial.flush()

    def close(self) -> None:
        """Cierra el puerto serie si está abierto."""
        if self._serial is not None:
            if self._serial.is_open:
                self._serial.close()

            self._serial = None
