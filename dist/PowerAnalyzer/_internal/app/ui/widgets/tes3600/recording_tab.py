# Registro de mediciones
"""Interfaz de registro de mediciones del Power Analyzer."""

from __future__ import annotations

import csv
import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QTime, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDateEdit,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabBar,
    QTabWidget,
    QTimeEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.base_tool import DeviceToolWidget


# Paleta de colores refinada para tema claro
COLORS = {
    "Sin datos": "#64748B",
    "Recibiendo": "#047857",
    "Sin señal": "#B91C1C",
    "Detenido": "#B91C1C",
    "Registrando": "#1D4ED8",
    "Finalizado": "#047857",
}

STATUS_BADGES = {
    "Sin datos": {
        "text": "●  Sin datos",
        "color": "#64748B",
        "bg": "#F1F5F9",
        "border": "#E2E8F0",
    },
    "Recibiendo": {
        "text": "●  Recibiendo",
        "color": "#047857",
        "bg": "#ECFDF5",
        "border": "#A7F3D0",
    },
    "Sin señal": {
        "text": "●  Sin señal",
        "color": "#B91C1C",
        "bg": "#FEF2F2",
        "border": "#FECACA",
    },
}

STATUS_TOOLTIPS = {
    "Sin datos": "No se han recibido mediciones todavía.",
    "Recibiendo": "La conexión está entregando datos.",
    "Sin señal": "La conexión está establecida, pero no llegan datos.",
}

EXPORT_FORMATS = {
    "Excel (.xlsx)": ("xlsx", "Libro de Excel (*.xlsx)"),
    "CSV (.csv)": ("csv", "CSV (*.csv)"),
    "Texto (.txt)": ("txt", "Texto (*.txt)"),
    "PDF (.pdf)": ("pdf", "PDF (*.pdf)"),
}
IMPORT_FILE_FILTER = (
    "Archivos compatibles (*.xlsx *.csv *.txt *.pdf);;"
    "Excel (*.xlsx);;CSV (*.csv);;Texto (*.txt);;PDF (*.pdf)"
)
FILE_FORMAT_VERSION = "PowerAnalyzerRecording/1"

CANONICAL_HEADERS = [
    "V1", "I1", "kVA1", "kW1", "FP1", "kVAR1", "Theta1",
    "V2", "I2", "kVA2", "kW2", "FP2", "kVAR2", "Theta2",
    "V3", "I3", "kVA3", "kW3", "FP3", "kVAR3", "Theta3",
    "TkVA", "TkW", "TFP", "TkVAR", "TTheta1", "Hz", "I4",
]


def order_headers_like_history(headers: list[str]) -> list[str]:
    """Ordena los encabezados siguiendo el orden canónico de historial (V1, I1, ...).

    Cualquier encabezado desconocido o adicional se mantiene al final.
    """
    header_set = set(headers)
    ordered = [h for h in CANONICAL_HEADERS if h in header_set]
    remaining = [h for h in headers if h not in ordered]
    return ordered + remaining


def format_timestamp_display(value: Any) -> str:
    """Formatea una estampa de tiempo o fecha para presentación en formato DD-MM-AAAA.

    Conserva la hora y la precisión temporal exactas.
    """
    if isinstance(value, datetime):
        base = value.strftime("%d-%m-%Y %H:%M:%S")
        if value.microsecond:
            ms = value.microsecond // 1000
            return f"{base}.{ms:03d}"
        return base

    if not isinstance(value, str):
        return str(value) if value is not None else ""

    text = value.strip()
    if not text:
        return ""

    # YYYY-MM-DD... -> DD-MM-YYYY...
    iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(.*)$", text)
    if iso_match:
        year, month, day, rest = iso_match.groups()
        if rest.startswith("T"):
            rest = " " + rest[1:]
        return f"{day}-{month}-{year}{rest}"

    # Si ya contiene DD-MM-YYYY o DD/MM/YYYY
    if re.match(r"^\d{2}[-/]\d{2}[-/]\d{4}", text):
        if "T" in text:
            return text.replace("T", " ")
        return text

    return text


def parse_timestamp(value: Any) -> datetime | None:
    """Parsea una estampa de tiempo en formatos ISO o DD-MM-AAAA."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    # Intentar formato ISO estándar primero (YYYY-MM-DD...)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    clean_text = text.replace("T", " ")
    for fmt in (
        "%d-%m-%Y %H:%M:%S.%f",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(clean_text, fmt)
        except ValueError:
            pass

    return None


def normalize_to_iso_timestamp(value: Any) -> str:
    """Normaliza una estampa de tiempo a formato ISO 8601 para almacenamiento interno."""
    if isinstance(value, datetime):
        if value.microsecond:
            return value.isoformat(sep=" ", timespec="milliseconds")
        return value.isoformat(sep=" ", timespec="seconds")

    if not isinstance(value, str):
        return str(value) if value is not None else ""

    text = value.strip()
    if not text:
        return ""

    # DD-MM-YYYY... -> YYYY-MM-DD...
    dmy_match = re.match(r"^(\d{2})-(\d{2})-(\d{4})(.*)$", text)
    if dmy_match:
        day, month, year, rest = dmy_match.groups()
        if rest.startswith("T"):
            rest = " " + rest[1:]
        return f"{year}-{month}-{day}{rest}"

    slash_match = re.match(r"^(\d{2})/(\d{2})/(\d{4})(.*)$", text)
    if slash_match:
        day, month, year, rest = slash_match.groups()
        if rest.startswith("T"):
            rest = " " + rest[1:]
        return f"{year}-{month}-{day}{rest}"

    return text


def _create_plus_icon() -> QIcon:
    """Ícono de vector '+' para nuevo registro."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#FFFFFF"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(16, 8, 16, 24)
    p.drawLine(8, 16, 24, 16)
    p.end()
    return QIcon(pix)


def _create_stop_icon() -> QIcon:
    """Ícono de vector '⏹' para detener registro."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#FFFFFF"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(9, 9, 14, 14), 3, 3)
    p.end()
    return QIcon(pix)


def _create_delete_icon() -> QIcon:
    """Ícono de vector para borrar registro."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#DC2626"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(9, 11, 23, 11)
    p.drawLine(13, 8, 19, 8)
    path = QPainterPath()
    path.moveTo(11, 11)
    path.lineTo(12, 24)
    path.lineTo(20, 24)
    path.lineTo(21, 11)
    p.drawPath(path)
    p.drawLine(14, 14, 14, 21)
    p.drawLine(18, 14, 18, 21)
    p.end()
    return QIcon(pix)


def _create_preview_icon() -> QIcon:
    """Ícono de vector de ojo para previsualización."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#334155"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(7, 16)
    path.quadTo(16, 8, 25, 16)
    path.quadTo(16, 24, 7, 16)
    p.drawPath(path)
    p.setBrush(QColor("#334155"))
    p.drawEllipse(QRectF(13.5, 13.5, 5, 5))
    p.end()
    return QIcon(pix)


def _create_export_icon() -> QIcon:
    """Ícono de vector de descarga/exportar."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#334155"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(16, 7, 16, 19)
    p.drawLine(12, 15, 16, 19)
    p.drawLine(20, 15, 16, 19)
    p.drawLine(9, 21, 9, 25)
    p.drawLine(9, 25, 23, 25)
    p.drawLine(23, 25, 23, 21)
    p.end()
    return QIcon(pix)


def _create_download_icon() -> QIcon:
    """Ícono de vector para descarga histórica desde servidor."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#334155"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(16, 6, 16, 18)
    p.drawLine(12, 14, 16, 18)
    p.drawLine(20, 14, 16, 18)
    p.drawLine(8, 22, 24, 22)
    p.drawLine(8, 26, 24, 26)
    p.end()
    return QIcon(pix)


RECORDING_TAB_STYLE = """
    QWidget#recording_tab {
        background-color: #F8FAFC;
    }

    /* Pestañas internas de la vista de registro */
    QTabWidget#recording_inner_tabs::pane {
        border: none;
        background-color: transparent;
    }
    QTabWidget#recording_inner_tabs > QTabBar::tab {
        background-color: #E2E8F0;
        color: #475569;
        font-family: "Segoe UI";
        font-weight: 600;
        font-size: 9pt;
        padding: 6px 14px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 4px;
    }
    QTabWidget#recording_inner_tabs > QTabBar::tab:selected {
        background-color: #FFFFFF;
        color: #0F172A;
        border: 1px solid #CBD5E1;
        border-bottom: 1px solid #FFFFFF;
    }
    QTabWidget#recording_inner_tabs > QTabBar::tab:hover:!selected {
        background-color: #EDF2F7;
        color: #1E293B;
    }

    /* Contenedor tipo tarjeta para la barra de herramientas */
    QFrame#recording_toolbar_card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
    }

    /* Botón principal: Nuevo Registro */
    QPushButton#btn_new_recording {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10B981, stop:1 #059669);
        color: #FFFFFF;
        border: 1px solid #047857;
        border-radius: 6px;
        padding: 7px 16px;
        font-family: "Segoe UI";
        font-weight: 600;
        font-size: 9.5pt;
    }
    QPushButton#btn_new_recording:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34D399, stop:1 #10B981);
        border: 1px solid #059669;
    }
    QPushButton#btn_new_recording:pressed {
        background: #047857;
        border: 1px solid #065F46;
    }
    QPushButton#btn_new_recording:disabled {
        background: #F1F5F9;
        color: #94A3B8;
        border: 1px solid #E2E8F0;
    }

    /* Botón de acción: Detener Registro */
    QPushButton#btn_stop_recording {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EF4444, stop:1 #DC2626);
        color: #FFFFFF;
        border: 1px solid #B91C1C;
        border-radius: 6px;
        padding: 7px 16px;
        font-family: "Segoe UI";
        font-weight: 600;
        font-size: 9.5pt;
    }
    QPushButton#btn_stop_recording:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F87171, stop:1 #EF4444);
        border: 1px solid #DC2626;
    }
    QPushButton#btn_stop_recording:pressed {
        background: #B91C1C;
        border: 1px solid #991B1B;
    }
    QPushButton#btn_stop_recording:disabled {
        background: #F1F5F9;
        color: #94A3B8;
        border: 1px solid #E2E8F0;
    }

    /* Botón de acción: Borrar Registro (outline elegante) */
    QPushButton#btn_delete_recording {
        background-color: #FFFFFF;
        color: #DC2626;
        border: 1px solid #FECACA;
        border-radius: 6px;
        padding: 7px 14px;
        font-family: "Segoe UI";
        font-weight: 600;
        font-size: 9.5pt;
    }
    QPushButton#btn_delete_recording:hover {
        background-color: #FEF2F2;
        border: 1px solid #F87171;
        color: #B91C1C;
    }
    QPushButton#btn_delete_recording:pressed {
        background-color: #FEE2E2;
        border: 1px solid #EF4444;
    }
    QPushButton#btn_delete_recording:disabled {
        background: #F8FAFC;
        color: #CBD5E1;
        border: 1px solid #E2E8F0;
    }

    /* Botones secundarios: Previsualización y Exportar */
    QPushButton#btn_preview_recording,
    QPushButton#btn_export_recording {
        background-color: #FFFFFF;
        color: #334155;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 7px 14px;
        font-family: "Segoe UI";
        font-weight: 600;
        font-size: 9.5pt;
    }
    QPushButton#btn_preview_recording:hover,
    QPushButton#btn_export_recording:hover {
        background-color: #F1F5F9;
        border: 1px solid #94A3B8;
        color: #0F172A;
    }
    QPushButton#btn_preview_recording:pressed,
    QPushButton#btn_export_recording:pressed {
        background-color: #E2E8F0;
        border: 1px solid #64748B;
    }
    QPushButton#btn_preview_recording:disabled,
    QPushButton#btn_export_recording:disabled {
        background: #F8FAFC;
        color: #CBD5E1;
        border: 1px solid #E2E8F0;
    }

    /* Separador vertical de la barra */
    QFrame#toolbar_separator {
        color: #E2E8F0;
        background-color: #E2E8F0;
        width: 1px;
        max-height: 24px;
        margin: 0px 4px;
    }

    /* Etiqueta de estado */
    QLabel#connection_label {
        color: #64748B;
        font-family: "Segoe UI";
        font-size: 9pt;
        font-weight: 600;
    }

    /* Tabla con tema claro moderno */
    QTableWidget {
        background-color: #FFFFFF;
        alternate-background-color: #F8FAFC;
        color: #1E293B;
        gridline-color: #F1F5F9;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        selection-background-color: #E0F2FE;
        selection-color: #0369A1;
        outline: none;
        font-family: "Segoe UI";
        font-size: 9.5pt;
    }
    QTableWidget::item {
        padding: 8px 12px;
        border-bottom: 1px solid #F1F5F9;
    }
    QTableWidget::item:selected {
        background-color: #E0F2FE;
        color: #0369A1;
    }
    QHeaderView::section {
        background-color: #F8FAFC;
        color: #475569;
        font-family: "Segoe UI";
        font-weight: 600;
        font-size: 9pt;
        padding: 9px 12px;
        border: none;
        border-bottom: 2px solid #E2E8F0;
        border-right: 1px solid #F1F5F9;
    }
    QScrollBar:vertical {
        border: none;
        background: #F8FAFC;
        width: 8px;
        margin: 0px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #CBD5E1;
        min-height: 25px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical:hover {
        background: #94A3B8;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        border: none;
        background: #F8FAFC;
        height: 8px;
        margin: 0px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal {
        background: #CBD5E1;
        min-width: 25px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #94A3B8;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
"""


@dataclass
class Recording:
    """Datos y estado de un registro almacenado en memoria."""

    record_id: int
    name: str
    started_at: datetime
    duration_seconds: int
    sample_interval_seconds: float
    status: str = "Registrando"
    stop_reason: str | None = None
    headers: list[str] = field(default_factory=list)
    samples: list[list[Any]] = field(default_factory=list)
    monotonic_start: float = field(default_factory=time.monotonic)
    last_sample_time: float = 0.0


class NewRecordingDialog(QDialog):
    """Configuración de un nuevo registro con tema claro moderno."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo registro")
        self.setModal(True)
        self.setMinimumWidth(390)

        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
                font-family: "Segoe UI";
            }
            QLabel#dialog_title {
                color: #1E293B;
                font-size: 11pt;
                font-weight: 600;
            }
            QLabel#dialog_subtitle {
                color: #64748B;
                font-size: 9pt;
            }
            QLabel {
                color: #334155;
                font-size: 9.5pt;
                font-weight: 500;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #FFFFFF;
                color: #1E293B;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 9.5pt;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1.5px solid #059669;
            }
            QPushButton {
                border-radius: 6px;
                padding: 7px 18px;
                font-family: "Segoe UI";
                font-size: 9.5pt;
                font-weight: 600;
            }
            QPushButton#btn_start {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                border: 1px solid #047857;
            }
            QPushButton#btn_start:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34D399, stop:1 #10B981);
                border: 1px solid #059669;
            }
            QPushButton#btn_start:pressed {
                background: #047857;
            }
            QPushButton#btn_cancel {
                background-color: #FFFFFF;
                color: #475569;
                border: 1px solid #CBD5E1;
            }
            QPushButton#btn_cancel:hover {
                background-color: #F1F5F9;
                border-color: #94A3B8;
                color: #0F172A;
            }
            QPushButton#btn_cancel:pressed {
                background-color: #E2E8F0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        title_lbl = QLabel("Nuevo registro de mediciones")
        title_lbl.setObjectName("dialog_title")
        subtitle_lbl = QLabel("Configurá los parámetros de adquisición de datos")
        subtitle_lbl.setObjectName("dialog_subtitle")
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(subtitle_lbl)
        layout.addLayout(header_layout)

        form = QFormLayout()
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej.: Ensayo de carga")

        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 86400)
        self.duration_input.setValue(60)
        self.duration_input.setSuffix(" s")

        self.interval_input = QDoubleSpinBox()
        self.interval_input.setRange(0.01, 3600.0)
        self.interval_input.setDecimals(2)
        self.interval_input.setSingleStep(0.1)
        self.interval_input.setValue(0.5)
        self.interval_input.setSuffix(" s")

        form.addRow("Nombre:", self.name_input)
        form.addRow("Duración:", self.duration_input)
        form.addRow("Tiempo entre muestras:", self.interval_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        self.start_button = buttons.addButton(
            " Iniciar", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.start_button.setObjectName("btn_start")
        self.start_button.setIcon(_create_plus_icon())
        self.start_button.setIconSize(QSize(14, 14))
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.cancel_button = buttons.addButton(
            "Cancelar", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.cancel_button.setObjectName("btn_cancel")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.start_button.clicked.connect(self._accept_if_valid)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if not self.name_input.text().strip():
            QMessageBox.warning(
                self, "Nombre requerido",
                "Ingresá un nombre para el registro."
            )
            return
        self.accept()

    def get_values(self) -> tuple[str, int, float]:
        return (
            self.name_input.text().strip(),
            self.duration_input.value(),
            self.interval_input.value(),
        )


IMPORT_DIALOG_STYLE = """
    QDialog {
        background-color: #F8FAFC;
        font-family: "Segoe UI";
    }
    QLabel {
        color: #334155;
        font-family: "Segoe UI";
        font-size: 9.5pt;
        font-weight: 500;
    }
    QLineEdit, QDateEdit, QTimeEdit {
        background-color: #FFFFFF;
        color: #1E293B;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 6px 10px;
        font-family: "Segoe UI";
        font-size: 9.5pt;
        selection-background-color: #E0F2FE;
        selection-color: #0369A1;
    }
    QLineEdit:focus, QDateEdit:focus, QTimeEdit:focus {
        border: 1.5px solid #059669;
    }
    QDateEdit::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 24px;
        border-left: 1px solid #CBD5E1;
        border-top-right-radius: 5px;
        border-bottom-right-radius: 5px;
        background-color: #F8FAFC;
    }
    QDateEdit::drop-down:hover {
        background-color: #E2E8F0;
    }
    QDateEdit::down-arrow {
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid #475569;
        width: 0px;
        height: 0px;
    }
    QDateEdit::down-arrow:hover {
        border-top-color: #0F172A;
    }
    QTimeEdit::up-button, QDateEdit::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 18px;
        border-left: 1px solid #CBD5E1;
        border-bottom: 1px solid #E2E8F0;
        border-top-right-radius: 5px;
        background-color: #F8FAFC;
    }
    QTimeEdit::up-button:hover, QDateEdit::up-button:hover {
        background-color: #E2E8F0;
    }
    QTimeEdit::up-arrow, QDateEdit::up-arrow {
        border-left: 3px solid transparent;
        border-right: 3px solid transparent;
        border-bottom: 4px solid #475569;
        width: 0px;
        height: 0px;
    }
    QTimeEdit::down-button, QDateEdit::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 18px;
        border-left: 1px solid #CBD5E1;
        border-bottom-right-radius: 5px;
        background-color: #F8FAFC;
    }
    QTimeEdit::down-button:hover, QDateEdit::down-button:hover {
        background-color: #E2E8F0;
    }
    QTimeEdit::down-arrow, QDateEdit::down-arrow {
        border-left: 3px solid transparent;
        border-right: 3px solid transparent;
        border-top: 4px solid #475569;
        width: 0px;
        height: 0px;
    }
    QDialogButtonBox QPushButton {
        background-color: #FFFFFF;
        color: #475569;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 7px 18px;
        font-family: "Segoe UI";
        font-size: 9.5pt;
        font-weight: 600;
        min-width: 75px;
    }
    QDialogButtonBox QPushButton:hover {
        background-color: #F1F5F9;
        border-color: #94A3B8;
        color: #0F172A;
    }
    QDialogButtonBox QPushButton:pressed {
        background-color: #E2E8F0;
    }
    QDialogButtonBox QPushButton:default {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10B981, stop:1 #059669);
        color: #FFFFFF;
        border: 1px solid #047857;
    }
    QDialogButtonBox QPushButton:default:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34D399, stop:1 #10B981);
        border: 1px solid #059669;
    }
"""

CALENDAR_POPUP_STYLE = """
    QCalendarWidget {
        background-color: #FFFFFF;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        font-family: "Segoe UI";
    }
    QCalendarWidget QWidget#qt_calendar_navigationbar {
        background-color: #F8FAFC;
        border-bottom: 1px solid #E2E8F0;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        min-height: 34px;
    }
    QCalendarWidget QToolButton {
        color: #1E293B;
        background-color: transparent;
        font-family: "Segoe UI";
        font-size: 9.5pt;
        font-weight: 600;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px 8px;
        margin: 2px;
    }
    QCalendarWidget QToolButton:hover {
        background-color: #E2E8F0;
        border-color: #CBD5E1;
        color: #0F172A;
    }
    QCalendarWidget QToolButton:pressed {
        background-color: #CBD5E1;
    }
    QCalendarWidget QMenu {
        background-color: #FFFFFF;
        color: #1E293B;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 4px;
    }
    QCalendarWidget QMenu::item:selected {
        background-color: #E0F2FE;
        color: #0369A1;
    }
    QCalendarWidget QSpinBox#qt_calendar_yearedit {
        background-color: #FFFFFF;
        color: #1E293B;
        border: 1px solid #CBD5E1;
        border-radius: 4px;
        padding: 2px 4px;
        font-size: 9.5pt;
        selection-background-color: #E0F2FE;
        selection-color: #0369A1;
    }
    QCalendarWidget QTableView#qt_calendar_calendarview {
        background-color: #FFFFFF;
        alternate-background-color: #FFFFFF;
        color: #1E293B;
        border: none;
        gridline-color: #F1F5F9;
        selection-background-color: #0284C7;
        selection-color: #FFFFFF;
        font-family: "Segoe UI";
        font-size: 9pt;
        outline: none;
    }
    QCalendarWidget QTableView#qt_calendar_calendarview::item:hover {
        background-color: #E0F2FE;
        color: #0369A1;
        border-radius: 4px;
    }
    QCalendarWidget QTableView#qt_calendar_calendarview::item:selected {
        background-color: #0284C7;
        color: #FFFFFF;
        font-weight: 600;
        border-radius: 4px;
    }
    QCalendarWidget QAbstractItemView:disabled {
        color: #94A3B8;
    }
    QCalendarWidget QHeaderView::section {
        background-color: #F8FAFC;
        color: #475569;
        font-family: "Segoe UI";
        font-weight: 600;
        font-size: 8.5pt;
        border: none;
        border-bottom: 1px solid #E2E8F0;
        padding: 3px;
    }
"""


class ImportRecordingDetailsDialog(QDialog):
    """Solicita nombre y fecha/hora para un registro importado."""

    def __init__(
        self,
        default_name: str,
        parent: QWidget | None = None,
        default_datetime: datetime | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Datos del registro importado")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setStyleSheet(IMPORT_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setSpacing(10)

        initial_dt = default_datetime or datetime.now()

        self.name_input = QLineEdit(default_name)
        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd-MM-yyyy")
        self.date_input.setDate(QDate(initial_dt.year, initial_dt.month, initial_dt.day))

        cal = self.date_input.calendarWidget()
        if cal:
            cal.setStyleSheet(CALENDAR_POPUP_STYLE)
            if cal.parent():
                cal.parent().setStyleSheet(CALENDAR_POPUP_STYLE)

        self.time_input = QTimeEdit()
        self.time_input.setDisplayFormat("HH:mm:ss")
        self.time_input.setTime(QTime(initial_dt.hour, initial_dt.minute, initial_dt.second))

        form.addRow("Nombre del registro:", self.name_input)
        form.addRow("Fecha de inicio:", self.date_input)
        form.addRow("Hora de inicio:", self.time_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if not self.name_input.text().strip():
            QMessageBox.warning(
                self, "Nombre requerido", "Ingresá un nombre para el registro."
            )
            return
        self.accept()

    def get_values(self) -> tuple[str, datetime]:
        selected_date = self.date_input.date()
        selected_time = self.time_input.time()
        return (
            self.name_input.text().strip(),
            datetime(
                selected_date.year(), selected_date.month(), selected_date.day(),
                selected_time.hour(), selected_time.minute(), selected_time.second(),
            ),
        )


class RecordingPreviewWindow(QMainWindow):
    """Ventana independiente para consultar las muestras de un registro."""

    closed = Signal(object)

    def __init__(self, recording: Recording, parent=None):
        super().__init__(parent)
        self.recording = recording

        self.setWindowTitle(f"Previsualización: {recording.name}")
        self.resize(1000, 600)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #F8FAFC;
                font-family: "Segoe UI";
            }
            QFrame#preview_header_card {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QLabel#preview_info {
                color: #334155;
                font-size: 9.5pt;
                font-weight: 600;
            }
            QTableWidget {
                background-color: #FFFFFF;
                alternate-background-color: #F8FAFC;
                color: #1E293B;
                gridline-color: #F1F5F9;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                selection-background-color: #E0F2FE;
                selection-color: #0369A1;
                outline: none;
                font-family: "Segoe UI";
                font-size: 9.5pt;
            }
            QTableWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #F1F5F9;
            }
            QTableWidget::item:selected {
                background-color: #E0F2FE;
                color: #0369A1;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #475569;
                font-family: "Segoe UI";
                font-weight: 600;
                font-size: 9pt;
                padding: 8px 10px;
                border: none;
                border-bottom: 2px solid #E2E8F0;
                border-right: 1px solid #F1F5F9;
            }
        """)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        header_card = QFrame()
        header_card.setObjectName("preview_header_card")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(14, 10, 14, 10)

        self.info_label = QLabel()
        self.info_label.setObjectName("preview_info")
        header_layout.addWidget(self.info_label)
        header_layout.addStretch()

        layout.addWidget(header_card)

        self.table = QTableWidget()
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        layout.addWidget(self.table)

        self.setCentralWidget(central)
        self._rendered_rows = 0
        self._rendered_headers = None
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh()

        if self.recording.status == "Registrando":
            self.refresh_timer.start()


    def refresh(self) -> None:
        recording = self.recording

        self.info_label.setText(
            f"Registro: {recording.name}  |  "
            f"Estado: {recording.status}  |  "
            f"Muestras: {len(recording.samples)}"
        )

        headers = ["Estampa de tiempo", *recording.headers]

        # Configurar columnas solo cuando cambie el esquema.
        if headers != self._rendered_headers:
            self.table.setUpdatesEnabled(False)
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self._rendered_headers = headers
            self.table.setUpdatesEnabled(True)

        # Si no hay filas nuevas, no reconstruir la tabla.
        total_rows = len(recording.samples)

        if total_rows > self._rendered_rows:
            self.table.setUpdatesEnabled(False)

            try:
                for row_index in range(self._rendered_rows, total_rows):
                    sample = recording.samples[row_index]
                    self.table.insertRow(row_index)

                    for column_index, value in enumerate(sample):
                        display_text = format_timestamp_display(value) if column_index == 0 else str(value)
                        item = QTableWidgetItem(display_text)

                        if column_index == 0:
                            item.setTextAlignment(
                                Qt.AlignmentFlag.AlignCenter
                            )
                        else:
                            item.setTextAlignment(
                                Qt.AlignmentFlag.AlignVCenter
                                | Qt.AlignmentFlag.AlignRight
                            )

                        self.table.setItem(row_index, column_index, item)

                self._rendered_rows = total_rows

            finally:
                self.table.setUpdatesEnabled(True)

        if recording.status != "Registrando":
            self.refresh_timer.stop()

    def closeEvent(self, event) -> None:
        """Detiene las actualizaciones cuando se cierra la ventana."""
        self.refresh_timer.stop()
        self.closed.emit(self)
        super().closeEvent(event)


class RecordingTab(DeviceToolWidget):
    """Pestaña de gestión de registros de mediciones."""

    connection_state_changed = Signal(str)

    recording_started = Signal(int, str, float)
    recording_stopped = Signal(int, str)
    recording_finished = Signal(int)
    recording_deleted = Signal(int)
    
    closed = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._recordings: dict[int, Recording] = {}
        self._previews: dict[int, list[RecordingPreviewWindow]] = {}
        self._next_id = 1
        self._connection_state = "Sin datos"
        self._active_device = None
        self._download_tab = None

        self._build_ui()

        self._duration_timer = QTimer(self)
        self._duration_timer.setInterval(100)
        self._duration_timer.timeout.connect(self._check_durations)
        self._duration_timer.start()

    def _on_preview_closed(self, window) -> None:
        """Elimina la referencia a una previsualización cerrada."""
        record_id = window.recording.record_id
        previews = self._previews.get(record_id, [])

        self._previews[record_id] = [
            preview
            for preview in previews
            if preview is not window
        ]

        if not self._previews[record_id]:
            self._previews.pop(record_id, None)
    
    def _build_ui(self) -> None:
        self.setObjectName("recording_tab")
        self.setStyleSheet(RECORDING_TAB_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # Contenedor de pestañas internas
        self.inner_tabs = QTabWidget(self)
        self.inner_tabs.setObjectName("recording_inner_tabs")
        self.inner_tabs.setDocumentMode(False)
        self.inner_tabs.setTabsClosable(True)
        self.inner_tabs.tabCloseRequested.connect(self._on_inner_tab_close_requested)

        # Pestaña 0: Registros (barra de herramientas + tabla)
        self.records_tab = QWidget()
        records_layout = QVBoxLayout(self.records_tab)
        records_layout.setContentsMargins(0, 0, 0, 0)
        records_layout.setSpacing(12)

        # Barra de herramientas con diseño de tarjeta
        toolbar_card = QFrame()
        toolbar_card.setObjectName("recording_toolbar_card")
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(12, 10, 12, 10)
        toolbar.setSpacing(8)

        self.new_button = QPushButton("  Nuevo Registro")
        self.new_button.setObjectName("btn_new_recording")
        self.new_button.setIcon(_create_plus_icon())
        self.new_button.setIconSize(QSize(15, 15))
        self.new_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.stop_button = QPushButton("  Detener Registro")
        self.stop_button.setObjectName("btn_stop_recording")
        self.stop_button.setIcon(_create_stop_icon())
        self.stop_button.setIconSize(QSize(15, 15))
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.delete_button = QPushButton("  Borrar Registro")
        self.delete_button.setObjectName("btn_delete_recording")
        self.delete_button.setIcon(_create_delete_icon())
        self.delete_button.setIconSize(QSize(15, 15))
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setObjectName("toolbar_separator")

        self.preview_button = QPushButton("  Previsualización")
        self.preview_button.setObjectName("btn_preview_recording")
        self.preview_button.setIcon(_create_preview_icon())
        self.preview_button.setIconSize(QSize(15, 15))
        self.preview_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.export_button = QPushButton("  Exportar")
        self.export_button.setObjectName("btn_export_recording")
        self.export_button.setIcon(_create_export_icon())
        self.export_button.setIconSize(QSize(15, 15))
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.import_button = QPushButton("  Importar")
        self.import_button.setObjectName("btn_export_recording")
        self.import_button.setIcon(_create_export_icon())
        self.import_button.setIconSize(QSize(15, 15))
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.download_button = QPushButton("  Descargar")
        self.download_button.setObjectName("btn_export_recording")
        self.download_button.setIcon(_create_download_icon())
        self.download_button.setIconSize(QSize(15, 15))
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)

        toolbar.addWidget(self.new_button)
        toolbar.addWidget(self.stop_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(separator)
        toolbar.addWidget(self.preview_button)
        toolbar.addWidget(self.export_button)
        toolbar.addWidget(self.import_button)
        toolbar.addWidget(self.download_button)

        toolbar.addStretch()

        connection_lbl = QLabel("Conexión:")
        connection_lbl.setObjectName("connection_label")
        toolbar.addWidget(connection_lbl)

        self.connection_indicator = QLabel("●  Sin datos")
        self.connection_indicator.setObjectName("connection_indicator")
        self.connection_indicator.setToolTip(
            STATUS_TOOLTIPS["Sin datos"]
        )
        toolbar.addWidget(self.connection_indicator)

        records_layout.addWidget(toolbar_card)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Fecha de inicio",
            "Nombre del registro",
            "Tiempo entre muestras",
            "Estado",
        ])
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        records_layout.addWidget(self.table)

        self.inner_tabs.addTab(self.records_tab, "Registros")
        # La pestaña de registros principal no debe cerrarse
        self.inner_tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.inner_tabs.tabBar().setVisible(False)

        root.addWidget(self.inner_tabs)

        self.new_button.clicked.connect(self._new_recording)
        self.stop_button.clicked.connect(self._stop_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.preview_button.clicked.connect(self._preview_selected)
        self.export_button.clicked.connect(self._export_selected)
        self.import_button.clicked.connect(self._import_recording)
        self.download_button.clicked.connect(self._open_download_tab)
        self.table.cellDoubleClicked.connect(
            lambda _row, _column: self._preview_selected()
        )

        self.set_connection_state("Sin datos")

    # ------------------------------------------------------------------
    # API pública para conectar la interfaz con el servicio de medición
    # ------------------------------------------------------------------

    def set_connection_state(self, state: str) -> None:
        """Estados admitidos: 'Sin datos', 'Recibiendo', 'Sin señal'."""
        if state not in ("Sin datos", "Recibiendo", "Sin señal"):
            raise ValueError(f"Estado de conexión desconocido: {state}")

        self._connection_state = state
        badge = STATUS_BADGES.get(
            state,
            {
                "text": f"●  {state}",
                "color": "#64748B",
                "bg": "#F1F5F9",
                "border": "#E2E8F0",
            },
        )
        self.connection_indicator.setText(badge["text"])
        self.connection_indicator.setStyleSheet(
            f"""
            QLabel#connection_indicator {{
                background-color: {badge['bg']};
                color: {badge['color']};
                border: 1px solid {badge['border']};
                border-radius: 13px;
                padding: 4px 14px;
                font-family: "Segoe UI";
                font-weight: 600;
                font-size: 9.5pt;
            }}
            """
        )
        self.connection_indicator.setToolTip(
            STATUS_TOOLTIPS.get(state, "")
        )
        self.connection_state_changed.emit(state)

    def active_recording_ids(self) -> list[int]:
        return [
            record_id
            for record_id, recording in self._recordings.items()
            if recording.status == "Registrando"
        ]

    def get_recording(self, record_id: int) -> Recording | None:
        return self._recordings.get(record_id)

    # ------------------------------------------------------------------
    # Contrato DeviceToolWidget
    # ------------------------------------------------------------------

    def on_measurements_received(self, measurements: dict[str, Any]) -> None:
        if not self.active_recording_ids():
            return
        timestamp = datetime.now()
        ordered_headers = order_headers_like_history(list(measurements.keys()))
        for record_id in self.active_recording_ids():
            self.add_sample(
                record_id=record_id,
                timestamp=timestamp,
                values=measurements,
                headers=ordered_headers,
            )

    def on_acquisition_status_changed(self, status: str) -> None:
        if status in ("Sin datos", "Recibiendo", "Sin señal"):
            self.set_connection_state(status)

    def on_device_connected(self, device: Any, service: Any = None) -> None:
        """Notifica que el dispositivo se ha conectado a la aplicación."""
        self._active_device = device
        if self._download_tab is not None:
            host = getattr(device, "host", "127.0.0.1") or "127.0.0.1"
            port = getattr(device, "history_port", 9001) or 9001
            self._download_tab.set_server_target(host, port)

    def on_device_disconnected(self) -> None:
        self._active_device = None
        self.set_connection_state("Sin datos")

    def _open_download_tab(self) -> None:
        """Abre o enfoca la pestaña interna de descarga desde el servidor."""
        if self._download_tab is not None:
            self.inner_tabs.setCurrentWidget(self._download_tab)
            return

        from app.ui.widgets.tes3600.history_download_widget import HistoryDownloadWidget

        host = "127.0.0.1"
        port = 9001
        if self._active_device is not None:
            host = getattr(self._active_device, "host", "127.0.0.1") or "127.0.0.1"
            port = getattr(self._active_device, "history_port", 9001) or 9001

        self._download_tab = HistoryDownloadWidget(
            default_host=host,
            default_port=port,
            parent=self,
        )
        self._download_tab.download_finished.connect(self._on_history_download_completed)
        self._download_tab.close_requested.connect(self._close_download_tab)

        index = self.inner_tabs.addTab(self._download_tab, "Descarga desde servidor")
        self.inner_tabs.setCurrentIndex(index)
        self.inner_tabs.tabBar().setVisible(True)

    def _close_download_tab(self) -> None:
        """Cierra la pestaña interna de descarga y regresa a la lista de registros."""
        if self._download_tab is not None:
            tab = self._download_tab
            self._download_tab = None
            idx = self.inner_tabs.indexOf(tab)
            if idx >= 0:
                self.inner_tabs.removeTab(idx)
            tab.deleteLater()

        self.inner_tabs.setCurrentWidget(self.records_tab)
        self.inner_tabs.tabBar().setVisible(self.inner_tabs.count() > 1)

    def _on_inner_tab_close_requested(self, index: int) -> None:
        """Maneja la solicitud de cierre de pestañas internas mediante el botón 'x'."""
        if index == 0:
            return  # La pestaña principal de registros no se puede cerrar
        widget = self.inner_tabs.widget(index)
        if widget is self._download_tab:
            self._close_download_tab()
        else:
            self.inner_tabs.removeTab(index)
            if widget is not None:
                widget.deleteLater()
            self.inner_tabs.tabBar().setVisible(self.inner_tabs.count() > 1)

    def _on_history_download_completed(self, result: dict) -> None:
        """Integra las mediciones históricas recibidas al sistema de registros o las exporta."""
        name = result.get("name", "Registro histórico")
        samples = result.get("samples", [])
        headers = result.get("headers", [])
        destination_mode = result.get("destination_mode", "internal")

        if not samples:
            QMessageBox.information(
                self,
                "Descarga completada",
                "La consulta finalizó correctamente pero no se encontraron mediciones para el período solicitado.",
            )
            self._close_download_tab()
            return

        save_internal = destination_mode in ("internal", "both")
        save_file = destination_mode in ("local_file", "both")

        recording_created = None
        if save_internal:
            record_id = self._next_id
            self._next_id += 1

            recording_created = Recording(
                record_id=record_id,
                name=name,
                started_at=result.get("started_at", datetime.now()),
                duration_seconds=result.get("duration_seconds", 1),
                sample_interval_seconds=result.get("sample_interval_seconds", 0.5),
                status="Finalizado",
                stop_reason="Descarga desde servidor",
                headers=headers,
                samples=samples,
                monotonic_start=time.monotonic(),
            )
            self._recordings[record_id] = recording_created
            self._refresh_table()
            self.table.selectRow(self.table.rowCount() - 1)

        if save_file:
            export_path = result.get("export_path")
            export_extension = result.get("export_extension")
            if not export_path or not export_extension:
                QMessageBox.critical(
                    self,
                    "Error de exportación",
                    "No se especificó la ruta o el formato para guardar el archivo local.",
                )
                return

            rec_for_export = recording_created if recording_created is not None else Recording(
                record_id=0,
                name=name,
                started_at=result.get("started_at", datetime.now()),
                duration_seconds=result.get("duration_seconds", 1),
                sample_interval_seconds=result.get("sample_interval_seconds", 0.5),
                status="Finalizado",
                stop_reason="Descarga desde servidor",
                headers=headers,
                samples=samples,
                monotonic_start=time.monotonic(),
            )

            try:
                self._write_recording_file(rec_for_export, Path(export_path), export_extension)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Error al guardar archivo",
                    f"No se pudo guardar el archivo exportado en la ruta elegida:\n\n{exc}",
                )
                return

        self._close_download_tab()

        if save_internal and save_file:
            QMessageBox.information(
                self,
                "Descarga completada",
                f"Se descargaron {len(samples):,} mediciones:\n\n"
                f"• Se incorporaron al registro interno «{name}» de Power Analyzer.\n"
                f"• Se exportaron exitosamente a:\n{result.get('export_path')}",
            )
        elif save_internal:
            QMessageBox.information(
                self,
                "Descarga completada",
                f"Se recibieron e incorporaron {len(samples):,} mediciones al nuevo registro «{name}» de Power Analyzer.",
            )
        elif save_file:
            QMessageBox.information(
                self,
                "Descarga completada",
                f"Se descargaron {len(samples):,} mediciones y se exportaron exitosamente a:\n{result.get('export_path')}",
            )

    def add_sample(
        self,
        record_id: int,
        timestamp: datetime | str,
        values: dict[str, Any] | list[Any] | tuple[Any, ...],
        headers: list[str] | None = None,
    ) -> bool:
        """
        Agrega una muestra al registro indicado.

        `values` puede ser un diccionario {nombre: valor} o una secuencia.
        Para secuencias, `headers` debe contener los nombres de las columnas.
        Devuelve False si el registro no existe, no está activo o todavía
        no corresponde tomar otra muestra según el intervalo configurado.
        """
        recording = self._recordings.get(record_id)
        if recording is None or recording.status != "Registrando":
            return False

        now = time.monotonic()
        if (
            recording.last_sample_time
            and now - recording.last_sample_time
            < recording.sample_interval_seconds
        ):
            return False

        if isinstance(timestamp, datetime):
            timestamp_text = timestamp.isoformat(sep=" ", timespec="milliseconds")
        else:
            timestamp_text = normalize_to_iso_timestamp(timestamp)

        if isinstance(values, dict):
            incoming_headers = order_headers_like_history(list(values.keys()))
            incoming_values = [values.get(h, "") for h in incoming_headers]
        else:
            incoming_values = list(values)
            incoming_headers = list(headers or [
                f"Dato {index + 1}"
                for index in range(len(incoming_values))
            ])

        # Mantiene el esquema estable si la primera muestra define las columnas.
        if not recording.headers:
            recording.headers = incoming_headers
            self._refresh_table()

        if incoming_headers != recording.headers:
            incoming_map = dict(zip(incoming_headers, incoming_values))
            incoming_values = [
                incoming_map.get(header, "")
                for header in recording.headers
            ]

        recording.samples.append([timestamp_text, *incoming_values])
        recording.last_sample_time = now
        self.set_connection_state("Recibiendo")
        self._refresh_previews(record_id)
        return True

    def stop_recording(self, record_id: int, reason: str) -> None:
        """Detiene un registro y conserva la causa exacta de la detención."""
        recording = self._recordings.get(record_id)
        if recording is None or recording.status != "Registrando":
            return

        recording.status = "Detenido"
        recording.stop_reason = reason
        self._refresh_table()
        self.recording_stopped.emit(record_id, reason)
        self._refresh_previews(record_id)

    # ------------------------------------------------------------------
    # Acciones de interfaz
    # ------------------------------------------------------------------

    def _new_recording(self) -> None:
        dialog = NewRecordingDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name, duration, interval = dialog.get_values()
        record_id = self._next_id
        self._next_id += 1

        recording = Recording(
            record_id=record_id,
            name=name,
            started_at=datetime.now(),
            duration_seconds=duration,
            sample_interval_seconds=interval,
        )
        self._recordings[record_id] = recording
        self._refresh_table()
        self.recording_started.emit(record_id, name, interval)

    def _selected_recording(self) -> Recording | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Selección requerida",
                "Seleccioná un registro de la tabla."
            )
            return None

        item = self.table.item(row, 0)
        if item is None:
            return None

        record_id = item.data(Qt.ItemDataRole.UserRole)
        return self._recordings.get(record_id)

    def _stop_selected(self) -> None:
        recording = self._selected_recording()
        if recording is None:
            return

        if recording.status != "Registrando":
            return

        self.stop_recording(recording.record_id, "Detención manual")

    def _delete_selected(self) -> None:
        recording = self._selected_recording()
        if recording is None:
            return

        answer = QMessageBox.question(
            self,
            "Borrar registro",
            f"¿Borrar el registro «{recording.name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if recording.status == "Registrando":
            self.stop_recording(
                recording.record_id,
                "Registro eliminado por el usuario",
            )

        self._recordings.pop(recording.record_id, None)

        for window in self._previews.pop(recording.record_id, []):
            window.close()

        self.recording_deleted.emit(recording.record_id)
        self._refresh_table()

    def _preview_selected(self) -> None:
        recording = self._selected_recording()
        if recording is None:
            return

        if recording.status == "Detenido":
            QMessageBox.information(
                self,
                "Registro detenido",
                f"Motivo de detención: "
                f"{recording.stop_reason or 'No especificado'}\n\n"
                f"Se mostrarán las {len(recording.samples)} muestras "
                "que se alcanzaron a guardar.",
            )

        window = RecordingPreviewWindow(recording)
        window.closed.connect(self._on_preview_closed)

        self._previews.setdefault(
            recording.record_id, []
        ).append(window)

        window.show()
        window.raise_()
        window.activateWindow()

    def _export_selected(self) -> None:
        recording = self._selected_recording()
        if recording is None:
            return

        selected, accepted = QInputDialog.getItem(
            self, "Exportar registro", "Formato:",
            list(EXPORT_FORMATS.keys()), 0, False,
        )
        if not accepted:
            return

        extension, file_filter = EXPORT_FORMATS[selected]
        suggested_name = self._safe_filename(recording.name) + f".{extension}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar registro", suggested_name, file_filter
        )
        if not path:
            return
        if Path(path).suffix.lower() != f".{extension}":
            path += f".{extension}"

        try:
            self._write_recording_file(recording, Path(path), extension)
        except Exception as exc:
            QMessageBox.critical(
                self, "Error de exportación",
                f"No se pudo exportar el registro.\\n\\nDetalle: {exc}",
            )
            return

        QMessageBox.information(
            self, "Exportación completada",
            f"El registro se exportó correctamente a:\\n{path}",
        )

    def _import_recording(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar registro", "", IMPORT_FILE_FILTER
        )
        if not path:
            return

        source = Path(path)
        extension = source.suffix.lower().lstrip(".")
        if extension not in {"xlsx", "csv", "txt", "pdf"}:
            QMessageBox.critical(
                self, "Formato no válido",
                "Solo se admiten archivos XLSX, CSV, TXT y PDF.",
            )
            return

        try:
            imported = self._read_recording_file(source, extension)
            if not imported["headers"] or not imported["samples"]:
                raise ValueError("El archivo no contiene encabezados y muestras.")
            expected_width = len(imported["headers"]) + 1
            for index, sample in enumerate(imported["samples"], start=1):
                if len(sample) != expected_width:
                    raise ValueError(
                        f"La muestra {index} tiene {len(sample)} columnas; "
                        f"se esperaban {expected_width}."
                    )
        except Exception as exc:
            QMessageBox.critical(
                self, "Archivo no válido",
                "No se pudo reconocer el archivo como un registro compatible "
                "de Power Analyzer.\\n\\n"
                f"Detalle: {exc}",
            )
            return

        metadata = imported.get("metadata") or {}
        started_at_str = metadata.get("started_at")
        default_dt = parse_timestamp(started_at_str) if started_at_str else None
        if default_dt is None and imported["samples"]:
            default_dt = parse_timestamp(imported["samples"][0][0])

        dialog = ImportRecordingDetailsDialog(
            source.stem, self, default_datetime=default_dt
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name, started_at = dialog.get_values()
        interval = self._estimate_sample_interval(imported["samples"])
        record_id = self._next_id
        self._next_id += 1
        recording = Recording(
            record_id=record_id,
            name=name,
            started_at=started_at,
            duration_seconds=1,
            sample_interval_seconds=interval,
            status="Finalizado",
            stop_reason="Registro importado",
            headers=imported["headers"],
            samples=imported["samples"],
            monotonic_start=time.monotonic(),
        )
        self._recordings[record_id] = recording
        self._refresh_table()
        self.table.selectRow(self.table.rowCount() - 1)
        QMessageBox.information(
            self, "Importación completada",
            f"Se importaron {len(recording.samples)} muestras.\\n"
            f"Tiempo entre muestras estimado: {interval:g} s.",
        )

    @staticmethod
    def _safe_filename(name: str) -> str:
        cleaned = "".join(
            char if char.isalnum() or char in (" ", "-", "_") else "_"
            for char in name
        ).strip()
        return cleaned or "registro"

    @staticmethod
    def _recording_metadata(recording: Recording) -> dict[str, Any]:
        return {
            "format": FILE_FORMAT_VERSION,
            "name": recording.name,
            "started_at": recording.started_at.isoformat(),
            "duration_seconds": recording.duration_seconds,
            "sample_interval_seconds": recording.sample_interval_seconds,
            "status": recording.status,
            "stop_reason": recording.stop_reason or "",
            "headers": recording.headers,
        }

    @classmethod
    def _write_recording_file(
        cls, recording: Recording, path: Path, extension: str
    ) -> None:
        metadata = cls._recording_metadata(recording)

        if extension == "csv":
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow([FILE_FORMAT_VERSION])
                writer.writerow(["metadata", json.dumps(metadata, ensure_ascii=False)])
                writer.writerow([])
                writer.writerow(["Estampa de tiempo", *recording.headers])
                for sample in recording.samples:
                    writer.writerow([format_timestamp_display(sample[0]), *sample[1:]])
            return

        if extension == "txt":
            with path.open("w", encoding="utf-8") as handle:
                handle.write(f"{FILE_FORMAT_VERSION}\n")
                handle.write(json.dumps(metadata, ensure_ascii=False) + "\n")
                handle.write("DATA\n")
                writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                writer.writerow(["Estampa de tiempo", *recording.headers])
                for sample in recording.samples:
                    writer.writerow([format_timestamp_display(sample[0]), *sample[1:]])
            return

        if extension == "xlsx":
            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font, PatternFill
            except ImportError as exc:
                raise RuntimeError(
                    "Para exportar XLSX instalá la dependencia: pip install openpyxl"
                ) from exc

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Registro"
            sheet.append([FILE_FORMAT_VERSION])
            sheet.append(["metadata", json.dumps(metadata, ensure_ascii=False)])
            sheet.append([])
            sheet.append(["Estampa de tiempo", *recording.headers])
            for sample in recording.samples:
                sheet.append([format_timestamp_display(sample[0]), *(str(value) for value in sample[1:])])
            for cell in sheet[4]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="334155")
            sheet.freeze_panes = "A5"
            for column_cells in sheet.columns:
                max_width = min(
                    max(len(str(cell.value or "")) for cell in column_cells) + 2,
                    35,
                )
                sheet.column_dimensions[column_cells[0].column_letter].width = max_width
            workbook.save(path)
            return

        if extension == "pdf":
            try:
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import landscape, A4
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import mm
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            except ImportError as exc:
                raise RuntimeError(
                    "Para exportar PDF instalá la dependencia: pip install reportlab"
                ) from exc

            rendered_path = path.with_name(path.stem + ".rendered.pdf")
            document = SimpleDocTemplate(
                str(rendered_path), pagesize=landscape(A4),
                rightMargin=12 * mm, leftMargin=12 * mm,
                topMargin=12 * mm, bottomMargin=12 * mm,
                title=f"Registro Power Analyzer: {recording.name}",
                author="Power Analyzer",
            )
            styles = getSampleStyleSheet()
            styles.add(ParagraphStyle(
                name="SmallCell", parent=styles["BodyText"],
                fontSize=6.5, leading=8, wordWrap="CJK",
            ))
            styles.add(ParagraphStyle(
                name="SmallHeaderCell", parent=styles["SmallCell"],
                fontName="Helvetica-Bold",
                textColor=colors.HexColor("#1E293B"),
            ))
            story = [
                Paragraph("Registro de mediciones - Power Analyzer", styles["Title"]),
                Spacer(1, 4 * mm),
                Paragraph(f"<b>Nombre:</b> {cls._html_escape(recording.name)}", styles["BodyText"]),
                Paragraph(f"<b>Fecha de inicio:</b> {format_timestamp_display(recording.started_at)}", styles["BodyText"]),
                Paragraph(f"<b>Estado:</b> {cls._html_escape(recording.status)}", styles["BodyText"]),
                Paragraph(f"<b>Tiempo entre muestras:</b> {recording.sample_interval_seconds:g} s", styles["BodyText"]),
                Paragraph(f"<b>Motivo:</b> {cls._html_escape(recording.stop_reason or 'No especificado')}", styles["BodyText"]),
                Spacer(1, 5 * mm),
            ]
            table_data = [[
                Paragraph(cls._html_escape(str(value)), styles["SmallHeaderCell"])
                for value in ["Estampa de tiempo", *recording.headers]
            ]]
            for sample in recording.samples:
                display_sample = [
                    format_timestamp_display(sample[0]),
                    *sample[1:],
                ]
                table_data.append([
                    Paragraph(cls._html_escape(str(value)), styles["SmallCell"])
                    for value in display_sample
                ])
            available_width = landscape(A4)[0] - 24 * mm
            column_width = available_width / max(1, len(recording.headers) + 1)
            table = Table(
                table_data,
                colWidths=[column_width] * (len(recording.headers) + 1),
                repeatRows=1,
            )
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B7B7B7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(table)
            document.build(story)

            # Adjuntar los datos estructurados evita meter miles de muestras
            # en los metadatos PDF, que tienen límites prácticos de tamaño.
            try:
                from pypdf import PdfReader, PdfWriter
            except ImportError as exc:
                rendered_path.unlink(missing_ok=True)
                raise RuntimeError(
                    "Para exportar/importar PDF instalá la dependencia: pip install pypdf"
                ) from exc

            payload = {
                "format": FILE_FORMAT_VERSION,
                "metadata": metadata,
                "headers": recording.headers,
                "samples": recording.samples,
            }
            try:
                reader = PdfReader(str(rendered_path))
                writer = PdfWriter()
                writer.clone_document_from_reader(reader)
                writer.add_metadata({
                    "/Title": f"Registro Power Analyzer: {recording.name}",
                    "/Author": "Power Analyzer",
                    "/Keywords": FILE_FORMAT_VERSION,
                })
                writer.add_attachment(
                    "power_analyzer_record.json",
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                )
                with path.open("wb") as output_handle:
                    writer.write(output_handle)
            finally:
                rendered_path.unlink(missing_ok=True)
            return

        raise ValueError(f"Formato de exportación desconocido: {extension}")

    @staticmethod
    def _html_escape(value: str) -> str:
        return (
            str(value).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;")
        )

    @staticmethod
    def _read_recording_file(path: Path, extension: str) -> dict[str, Any]:
        metadata = None
        headers: list[str] = []
        samples: list[list[Any]] = []

        if extension == "xlsx":
            try:
                from openpyxl import load_workbook
            except ImportError as exc:
                raise RuntimeError(
                    "Para importar XLSX instalá la dependencia: pip install openpyxl"
                ) from exc
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                rows = list(workbook.active.iter_rows(values_only=True))
            finally:
                workbook.close()
            if len(rows) < 4 or not rows[0] or rows[0][0] != FILE_FORMAT_VERSION:
                raise ValueError("No se encontró la firma de formato de Power Analyzer.")
            if not rows[1] or rows[1][0] != "metadata":
                raise ValueError("Faltan los metadatos del registro.")
            metadata = json.loads(rows[1][1])
            if metadata.get("format") != FILE_FORMAT_VERSION:
                raise ValueError("Versión de archivo no compatible.")
            headers = [str(value) for value in rows[3][1:] if value is not None]
            for row in rows[4:]:
                if row and row[0] is not None:
                    samples.append([str(value) if value is not None else "" for value in row[:len(headers)+1]])

        elif extension in {"csv", "txt"}:
            delimiter = "," if extension == "csv" else "\t"
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle, delimiter=delimiter))
            if len(rows) < 4 or not rows[0] or rows[0][0] != FILE_FORMAT_VERSION:
                raise ValueError("No se encontró la firma de formato de Power Analyzer.")
            if extension == "csv":
                if len(rows[1]) < 2 or rows[1][0] != "metadata":
                    raise ValueError("Faltan los metadatos del registro.")
                metadata = json.loads(rows[1][1])
            else:
                metadata = json.loads(rows[1][0])
                if not rows[2] or rows[2][0] != "DATA":
                    raise ValueError("No se encontró la sección de datos.")
            if metadata.get("format") != FILE_FORMAT_VERSION:
                raise ValueError("Versión de archivo no compatible.")
            headers = [value for value in rows[3][1:] if value]
            for row in rows[4:]:
                if row and row[0].strip():
                    samples.append([value for value in row[:len(headers)+1]])

        elif extension == "pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError(
                    "Para importar PDF instalá la dependencia: pip install pypdf"
                ) from exc
            reader = PdfReader(str(path))
            if not reader.pages:
                raise ValueError("El PDF no contiene páginas.")
            keywords = (reader.metadata or {}).get("/Keywords")
            if keywords != FILE_FORMAT_VERSION:
                raise ValueError(
                    "Este PDF no fue exportado por una versión compatible de Power Analyzer."
                )
            attachments = getattr(reader, "attachments", {})
            attachment_data = attachments.get("power_analyzer_record.json")
            if isinstance(attachment_data, list):
                attachment_data = attachment_data[0] if attachment_data else None
            if not attachment_data:
                raise ValueError("El PDF no contiene los datos del registro adjuntos.")
            payload = json.loads(attachment_data.decode("utf-8"))
            metadata = payload.get("metadata")
            headers = [str(value) for value in payload.get("headers", [])]
            samples = [
                [str(value) if value is not None else "" for value in row]
                for row in payload.get("samples", [])
            ]
            if payload.get("format") != FILE_FORMAT_VERSION:
                raise ValueError("Versión de PDF no compatible.")
        else:
            raise ValueError(f"Extensión no admitida: {extension}")

        if not isinstance(metadata, dict):
            raise ValueError("Los metadatos no son válidos.")
        if not headers:
            headers = [str(value) for value in metadata.get("headers", [])]
        if not headers:
            raise ValueError("No se encontraron columnas de medición.")

        normalized_samples = []
        for sample in samples:
            row = list(sample)
            if len(row) < len(headers) + 1:
                row.extend([""] * (len(headers) + 1 - len(row)))
            row[0] = normalize_to_iso_timestamp(row[0])
            normalized_samples.append(row[:len(headers) + 1])

        return {"metadata": metadata, "headers": headers, "samples": normalized_samples}

    @staticmethod
    def _estimate_sample_interval(samples: list[list[Any]]) -> float:
        """Estima el intervalo con la diferencia más frecuente entre las primeras 20 muestras."""
        parsed: list[datetime] = []
        for sample in samples[:20]:
            if not sample:
                continue
            dt = parse_timestamp(sample[0])
            if dt is not None:
                parsed.append(dt)

        differences = []
        for previous, current in zip(parsed, parsed[1:]):
            delta = (current - previous).total_seconds()
            if delta > 0 and math.isfinite(delta):
                differences.append(round(delta, 3))
        if not differences:
            return 0.0

        counts = Counter(differences)
        highest_count = max(counts.values())
        return float(min(
            value for value, count in counts.items() if count == highest_count
        ))

    # ------------------------------------------------------------------
    # Actualización de tabla y temporización
    # ------------------------------------------------------------------

    def _refresh_table(self) -> None:
        selected_id = None
        current_row = self.table.currentRow()
        if current_row >= 0 and self.table.item(current_row, 0):
            selected_id = self.table.item(
                current_row, 0
            ).data(Qt.ItemDataRole.UserRole)

        self.table.setRowCount(len(self._recordings))

        for row, recording in enumerate(self._recordings.values()):
            values = [
                format_timestamp_display(recording.started_at),
                recording.name,
                f"{recording.sample_interval_seconds:g} s",
                recording.status,
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(
                    item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, recording.record_id)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                elif column == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                elif column == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                elif column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    status_color = COLORS.get(recording.status, "#1E293B")
                    item.setForeground(QColor(status_color))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                self.table.setItem(row, column, item)

            if recording.record_id == selected_id:
                self.table.selectRow(row)

    def _refresh_previews(self, record_id: int) -> None:
        for window in self._previews.get(record_id, []):
            if window.isVisible():
                window.refresh()

    def _check_durations(self) -> None:
        now = time.monotonic()

        for recording in list(self._recordings.values()):
            if recording.status != "Registrando":
                continue

            elapsed = now - recording.monotonic_start
            if elapsed >= recording.duration_seconds:
                recording.status = "Finalizado"
                recording.stop_reason = "Duración completada"
                self._refresh_table()
                self.recording_finished.emit(recording.record_id)
                self._refresh_previews(recording.record_id)


class QInputDialogCompat:
    """Pequeño adaptador para mostrar el selector de formato."""

    @staticmethod
    def get_item(parent, title, label, items):
        from PySide6.QtWidgets import QInputDialog

        return QInputDialog.getItem(parent, title, label, items, 0, False)
