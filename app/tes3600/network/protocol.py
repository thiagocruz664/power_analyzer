from dataclasses import dataclass
import struct


from dataclasses import dataclass
from datetime import datetime
import struct


TIMESTAMP_SIZE_LEGACY = 4
TIMESTAMP_SIZE_UNIFIED = 8
TIMESTAMP_SIZE = TIMESTAMP_SIZE_LEGACY  # Compatibilidad

TES3600_FRAME_SIZE = 61
MESSAGE_SIZE_LEGACY = TIMESTAMP_SIZE_LEGACY + TES3600_FRAME_SIZE  # 65 bytes
MESSAGE_SIZE_UNIFIED = TIMESTAMP_SIZE_UNIFIED + TES3600_FRAME_SIZE  # 69 bytes
MESSAGE_SIZE = MESSAGE_SIZE_LEGACY  # Compatibilidad

HEADER_SIZE = 4
TOTAL_PACKET_SIZE_LEGACY = HEADER_SIZE + MESSAGE_SIZE_LEGACY  # 69 bytes
TOTAL_PACKET_SIZE_UNIFIED = HEADER_SIZE + MESSAGE_SIZE_UNIFIED  # 73 bytes


@dataclass
class ReceivedMessage:
    hour: int
    minute: int
    second: int
    millisecond: int
    frame: bytes
    timestamp: datetime | None = None
    unix_timestamp_ms: int | None = None


def parse_message(data: bytes) -> ReceivedMessage:
    """Separa la marca temporal y la trama TES3600.
    
    Identifica el formato mediante la longitud del contenido recibido:
    - 69 bytes: formato definitivo unificado (timestamp Unix de 8 bytes, big-endian)
    - 65 bytes: formato anterior (timestamp de 4 bytes ms desde medianoche, big-endian)
    """
    length = len(data)
    if length != MESSAGE_SIZE_UNIFIED and length != MESSAGE_SIZE_LEGACY:
        raise ValueError(
            f"Longitud incorrecta: se esperaban {MESSAGE_SIZE_UNIFIED} o {MESSAGE_SIZE_LEGACY} bytes, "
            f"se recibieron {length}."
        )

    if length == MESSAGE_SIZE_UNIFIED:
        # Formato definitivo unificado (8 bytes Unix timestamp en milisegundos)
        timestamp_bytes = data[:TIMESTAMP_SIZE_UNIFIED]
        frame = data[TIMESTAMP_SIZE_UNIFIED:]

        if frame[0] != 0x02 or frame[-1] != 0x03:
            raise ValueError(
                "Los delimitadores de la trama TES3600 son inválidos."
            )

        unix_ms = struct.unpack("!Q", timestamp_bytes)[0]
        dt = datetime.fromtimestamp(unix_ms / 1000.0)

        return ReceivedMessage(
            hour=dt.hour,
            minute=dt.minute,
            second=dt.second,
            millisecond=dt.microsecond // 1000,
            frame=frame,
            timestamp=dt,
            unix_timestamp_ms=unix_ms,
        )

    # Formato anterior legacy (4 bytes ms desde medianoche)
    timestamp_bytes = data[:TIMESTAMP_SIZE_LEGACY]
    frame = data[TIMESTAMP_SIZE_LEGACY:]

    if frame[0] != 0x02 or frame[-1] != 0x03:
        raise ValueError(
            "Los delimitadores de la trama TES3600 son inválidos."
        )

    timestamp_ms = struct.unpack("!I", timestamp_bytes)[0]

    if timestamp_ms >= 24 * 60 * 60 * 1000:
        raise ValueError(
            "La marca temporal contiene un valor fuera del día."
        )

    segundos_totales, millisecond = divmod(timestamp_ms, 1000)
    hour, resto = divmod(segundos_totales, 3600)
    minute, second = divmod(resto, 60)

    return ReceivedMessage(
        hour=hour,
        minute=minute,
        second=second,
        millisecond=millisecond,
        frame=frame,
        timestamp=None,
        unix_timestamp_ms=None,
    )
