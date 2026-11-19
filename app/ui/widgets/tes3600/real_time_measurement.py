# Medición en tiempo real
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.base_tool import DeviceToolWidget


class MeasurementCard(QFrame):
    """Panel individual con el nombre, valor y unidad de una medición."""

    def __init__(
        self,
        name,
        unit,
        background,
        border_color,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName("measurement_card")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(8)

        self.name_label = QLabel(name)
        self.name_label.setObjectName("measurement_name")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)

        self.value_label = QLabel("---")
        self.value_label.setObjectName("measurement_value")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.unit_label = QLabel(unit)
        self.unit_label.setObjectName("measurement_unit")
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.name_label)
        layout.addStretch(1)
        layout.addWidget(self.value_label)
        layout.addWidget(self.unit_label)
        layout.addStretch(1)

        self.setStyleSheet(
            f"""
            QFrame#measurement_card {{
                background-color: {background};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}

            QLabel#measurement_name {{
                color: #34495A;
                font-size: 10pt;
                font-weight: 600;
                border: none;
                background-color: transparent;
            }}

            QLabel#measurement_value {{
                color: #172A39;
                font-size: 17pt;
                font-weight: 600;
                border: none;
                background-color: transparent;
            }}

            QLabel#measurement_unit {{
                color: #627384;
                font-size: 9pt;
                border: none;
                background-color: transparent;
            }}
            """
        )

    def set_value(self, value):
        """Actualiza el valor mostrado en el panel."""
        self.value_label.setText(str(value))


class RealTimeMeasurementWidget(DeviceToolWidget):
    """Vista principal de mediciones eléctricas en tiempo real."""

    ROWS = [
        {
            "names": ["kW1", "kVAR1", "kVA1", "FP1", "Theta1", "V1", "I1"],
            "background": "#FCE8E8",
            "border": "#E8B7B7",
        },
        {
            "names": ["kW2", "kVAR2", "kVA2", "FP2", "Theta2", "V2", "I2"],
            "background": "#FFF4CC",
            "border": "#E6D58A",
        },
        {
            "names": ["kW3", "kVAR3", "kVA3", "FP3", "Theta3", "V3", "I3"],
            "background": "#DDF4FC",
            "border": "#A8D9E8",
        },
        {
            "names": ["TkW", "TkVAR", "TkVA", "TFP", "TTheta1", "Hz", "I4"],
            "background": "#FFFFFF",
            "border": "#CCD4DC",
        },
    ]

    UNITS = {
        "kW1": "kW",
        "kW2": "kW",
        "kW3": "kW",
        "TkW": "kW",
        "kVAR1": "kVAR",
        "kVAR2": "kVAR",
        "kVAR3": "kVAR",
        "TkVAR": "kVAR",
        "kVA1": "kVA",
        "kVA2": "kVA",
        "kVA3": "kVA",
        "TkVA": "kVA",
        "FP1": "",
        "FP2": "",
        "FP3": "",
        "TFP": "",
        "Theta1": "°",
        "Theta2": "°",
        "Theta3": "°",
        "TTheta1": "°",
        "V1": "V",
        "V2": "V",
        "V3": "V",
        "I1": "A",
        "I2": "A",
        "I3": "A",
        "I4": "A",
        "Hz": "Hz",
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("real_time_measurement")
        self.measurement_cards = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)

        # Cabecera: título a la izquierda y estado a la derecha.
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        title = QLabel("Medición en tiempo real")
        title.setObjectName("page_title")

        header_layout.addWidget(title)
        header_layout.addStretch(1)

        status_layout = QVBoxLayout()
        status_layout.setSpacing(5)

        self.acquisition_status = QLabel("Sin datos")
        self.acquisition_status.setObjectName("acquisition_status")
        self.acquisition_status.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        self.last_frame_label = QLabel(
            "Última trama válida: --:--:--"
        )
        self.last_frame_label.setObjectName("last_frame")
        self.last_frame_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        status_layout.addWidget(self.acquisition_status)
        status_layout.addWidget(self.last_frame_label)

        header_layout.addLayout(status_layout)
        main_layout.addLayout(header_layout)

        self._set_acquisition_status("Sin datos")

        # Cuadrícula de mediciones.
        grid = QGridLayout()
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        for row_index, row_data in enumerate(self.ROWS):
            for column_index, name in enumerate(row_data["names"]):
                card = MeasurementCard(
                    name=name,
                    unit=self.UNITS.get(name, ""),
                    background=row_data["background"],
                    border_color=row_data["border"],
                )

                grid.addWidget(card, row_index, column_index)
                self.measurement_cards[name] = card

        for column in range(7):
            grid.setColumnStretch(column, 1)

        for row in range(4):
            grid.setRowStretch(row, 1)

        main_layout.addLayout(grid, 1)

        self.setStyleSheet(
            """
            QLabel#acquisition_status {
                color: #8A6D1D;
                font-size: 10pt;
                font-weight: 600;
            }

            QLabel#last_frame {
                color: #627384;
                font-size: 9pt;
            }
            """
        )

    def _set_acquisition_status(self, status):
        """Actualiza el texto y el color del estado de adquisición."""
        colors = {
            "Sin datos": "#8A6D1D",
            "Recibiendo": "#247A46",
            "Sin señal": "#B33A3A",
        }

        color = colors.get(status, "#627384")

        self.acquisition_status.setText(status)
        self.acquisition_status.setStyleSheet(
            f"color: {color};"
        )

    def set_acquisition_status(self, status):
        """
        Estados previstos: 'Sin datos', 'Recibiendo' y 'Sin señal'.
        """
        self._set_acquisition_status(status)

    def set_last_valid_frame_time(self, timestamp=None):
        """
        Actualiza la hora de la última trama válida.

        Si no se proporciona timestamp, utiliza la hora actual.
        """
        if timestamp is None:
            timestamp = datetime.now()

        self.last_frame_label.setText(
            f"Última trama válida: {timestamp:%H:%M:%S}"
        )
        self._set_acquisition_status("Recibiendo")

    def set_measurement(self, name, value):
        """Actualiza una medición individual por su identificador."""
        card = self.measurement_cards.get(name)

        if card is not None:
            card.set_value(value)

    def update_measurements(self, measurements):
        """
        Actualiza varias mediciones a partir de un diccionario.

        Ejemplo:
            {
                "V1": "220.5",
                "I1": "2.34",
                "kW1": "0.48",
            }
        """
        for name, value in measurements.items():
            self.set_measurement(name, value)

    # ------------------------------------------------------------------
    # Contrato DeviceToolWidget
    # ------------------------------------------------------------------

    def on_measurements_received(self, measurements: dict) -> None:
        self.update_measurements(measurements)

    def on_valid_frame_received(self, timestamp: datetime) -> None:
        self.set_last_valid_frame_time(timestamp)

    def on_acquisition_status_changed(self, status: str) -> None:
        self.set_acquisition_status(status)

    def on_device_disconnected(self) -> None:
        self.set_acquisition_status("Sin señal")
