from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Measurement:
    """Representa una magnitud eléctrica medida o calculada."""

    name: str
    value: float
    unit: str
    timestamp: datetime
