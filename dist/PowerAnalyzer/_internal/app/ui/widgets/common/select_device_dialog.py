from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QComboBox,
    QDialogButtonBox,
)

from app.device_manager.device import Device


class SelectDeviceDialog(QDialog):
    def __init__(
        self,
        devices: list[Device],
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Conectar dispositivo")
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel("Seleccioná el dispositivo que querés conectar:")
        )

        form = QFormLayout()

        self.device_combo = QComboBox()

        for device in devices:
            connection_label = (
                "TCP"
                if device.connection_type == "tcp"
                else "Serie"
            )

            self.device_combo.addItem(
                f"{device.name} ({connection_label})",
                device.id,
            )

        form.addRow("Dispositivo:", self.device_combo)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Conectar")

        self.buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("Cancelar")

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout.addWidget(self.buttons)

    def selected_device_id(self) -> str | None:
        return self.device_combo.currentData()
