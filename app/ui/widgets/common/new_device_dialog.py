from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QRadioButton,
    QSpinBox,
    QDialogButtonBox,
    QMessageBox,
)


class NewDeviceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Nuevo dispositivo")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._create_ui()
        self._connect_signals()

        self.setStyleSheet(parent.styleSheet() if parent else "")
        
    def _create_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)

        # Información general
        general_group = QGroupBox("Información del dispositivo")
        general_form = QFormLayout(general_group)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej. TES Laboratorio")

        self.model_combo = QComboBox()
        self.model_combo.addItem("TES3600", "TES3600")

        general_form.addRow("Nombre:", self.name_input)
        general_form.addRow("Modelo:", self.model_combo)

        main_layout.addWidget(general_group)

        # Tipo de conexión
        connection_group = QGroupBox("Conexión")
        connection_layout = QVBoxLayout(connection_group)

        radio_layout = QHBoxLayout()

        self.tcp_radio = QRadioButton(
            "Red TCP (Raspberry Pi / ESP32)"
        )
        self.serial_radio = QRadioButton(
            "Serie local (desarrollo)"
        )

        self.tcp_radio.setChecked(True)

        radio_layout.addWidget(self.tcp_radio)
        radio_layout.addWidget(self.serial_radio)

        connection_layout.addLayout(radio_layout)

        # Parámetros de conexión
        self.connection_form = QFormLayout()

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText(
            "Ej. 192.168.1.50"
        )

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(5000)

        self.history_port_input = QSpinBox()
        self.history_port_input.setRange(1, 65535)
        self.history_port_input.setValue(9001)

        self.connection_form.addRow(
            "Dirección IP o host:",
            self.host_input,
        )
        self.connection_form.addRow(
            "Puerto TCP (tiempo real):",
            self.port_input,
        )
        self.connection_form.addRow(
            "Puerto TCP (histórico):",
            self.history_port_input,
        )

        connection_layout.addLayout(self.connection_form)

        self.connection_note = QLabel(
            "La dirección corresponde al servidor "
            "de la Raspberry Pi o ESP32."
        )
        self.connection_note.setWordWrap(True)
        self.connection_note.setStyleSheet(
            "color: gray; font-size: 11px;"
        )

        connection_layout.addWidget(self.connection_note)

        main_layout.addWidget(connection_group)

        # Descripción opcional
        description_group = QGroupBox("Descripción (opcional)")
        description_layout = QVBoxLayout(description_group)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText(
            "Ej. Laboratorio de electrónica"
        )

        description_layout.addWidget(self.description_input)
        main_layout.addWidget(description_group)

        # Botones
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        self.buttons.button(
            QDialogButtonBox.StandardButton.Save
        ).setText("Guardar")

        self.buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("Cancelar")

        main_layout.addWidget(self.buttons)

    def _connect_signals(self):
        self.tcp_radio.toggled.connect(
            self._update_connection_fields
        )

        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)

    def _update_connection_fields(self):
        is_tcp = self.tcp_radio.isChecked()

        self.connection_form.labelForField(
            self.host_input
        ).setText(
            "Dirección IP o host:" if is_tcp
            else "Puerto serie:"
        )

        self.port_input.setVisible(is_tcp)
        self.connection_form.labelForField(
            self.port_input
        ).setVisible(is_tcp)

        self.history_port_input.setVisible(is_tcp)
        self.connection_form.labelForField(
            self.history_port_input
        ).setVisible(is_tcp)

        self.host_input.clear()
        self.host_input.setPlaceholderText(
            "Ej. 192.168.1.50"
            if is_tcp
            else "Ej. COM8 o /dev/ttyUSB0"
        )

        self.connection_note.setText(
            "La dirección corresponde al servidor "
            "de la Raspberry Pi o ESP32."
            if is_tcp
            else "Conexión local para desarrollo y pruebas."
        )

    def _save(self):
        name = self.name_input.text().strip()
        host = self.host_input.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Dato obligatorio",
                "Ingresá un nombre para el dispositivo.",
            )
            self.name_input.setFocus()
            return

        if not host:
            field_name = (
                "la dirección IP o el host"
                if self.tcp_radio.isChecked()
                else "el puerto serie"
            )

            QMessageBox.warning(
                self,
                "Dato obligatorio",
                f"Ingresá {field_name}.",
            )
            self.host_input.setFocus()
            return

        self.accept()

    def get_device_config(self):
        is_tcp = self.tcp_radio.isChecked()

        config = {
            "name": self.name_input.text().strip(),
            "model": self.model_combo.currentData(),
            "connection_type": "tcp" if is_tcp else "serial",
            "description": self.description_input.text().strip(),
        }

        if is_tcp:
            config["host"] = self.host_input.text().strip()
            config["port"] = self.port_input.value()
            config["history_port"] = self.history_port_input.value()
        else:
            config["serial_port"] = self.host_input.text().strip()

        return config
