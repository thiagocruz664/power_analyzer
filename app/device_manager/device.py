from dataclasses import dataclass
from uuid import uuid4


@dataclass
class Device:
    name: str
    model: str
    connection_type: str
    description: str = ""
    host: str = ""
    port: int = 5000
    history_port: int = 9001
    serial_port: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())

        if self.connection_type not in {"tcp", "serial"}:
            raise ValueError("Tipo de conexión no válido.")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "connection_type": self.connection_type,
            "description": self.description,
            "host": self.host,
            "port": self.port,
            "history_port": self.history_port,
            "serial_port": self.serial_port,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Device":
        return cls(**data)
