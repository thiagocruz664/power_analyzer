"""Contrato base para herramientas de interfaz asociadas a dispositivos."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from PySide6.QtWidgets import QWidget


class DeviceToolWidget(QWidget):
    """Clase base para todos los widgets de herramientas de trabajo de dispositivos.

    Cualquier módulo de herramienta en app/ui/widgets/<dispositivo>/ debe exponer
    una clase que herede de esta para ser descubierta e instanciada automáticamente.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def on_measurements_received(self, measurements: dict[str, Any]) -> None:
        """Notifica nuevas mediciones recibidas del dispositivo conectado."""
        pass

    def on_valid_frame_received(self, timestamp: datetime) -> None:
        """Notifica la recepción de una trama válida con estampa de tiempo."""
        pass

    def on_acquisition_status_changed(self, status: str) -> None:
        """Notifica cambios en el estado de adquisición ('Sin datos', 'Recibiendo', 'Sin señal')."""
        pass

    def on_device_connected(self, device: Any, service: Any = None) -> None:
        """Notifica que el dispositivo se ha conectado a la aplicación."""
        pass

    def on_device_disconnected(self) -> None:
        """Notifica que el dispositivo activo se ha desconectado."""
        pass
