"""Panel y pestaña interna para la descarga de mediciones históricas del TES3600."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QTime, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.tes3600.services.history_service import HistoryDownloadWorker

EXPORT_FORMATS = {
    "Excel (.xlsx)": ("xlsx", "Libro de Excel (*.xlsx)"),
    "CSV (.csv)": ("csv", "CSV (*.csv)"),
    "Texto (.txt)": ("txt", "Texto (*.txt)"),
    "PDF (.pdf)": ("pdf", "PDF (*.pdf)"),
}

PERIOD_OPTIONS = [
    ("Última hora", 0x01),
    ("Últimas 3 horas", 0x02),
    ("Últimas 6 horas", 0x03),
    ("Últimas 12 horas", 0x04),
    ("Últimas 24 horas", 0x05),
    ("Últimos 3 días", 0x06),
    ("Últimos 7 días", 0x07),
    ("Últimos 15 días", 0x08),
    ("Últimos 30 días", 0x09),
    ("Personalizado", 0x0F),
]

DESTINATION_INTERNAL = "Guardar en Power Analyzer (registro interno)"
DESTINATION_LOCAL = "Descargar en archivo local"

DOWNLOAD_WIDGET_STYLE = """
    QWidget#history_download_page {
        background-color: #F8FAFC;
        font-family: "Segoe UI";
    }

    QFrame#card_container {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
    }

    QLabel#section_title {
        color: #0F172A;
        font-size: 11pt;
        font-weight: 700;
    }

    QLabel#section_subtitle {
        color: #64748B;
        font-size: 9pt;
        margin-bottom: 6px;
    }

    QLabel#form_label {
        color: #334155;
        font-size: 9.5pt;
        font-weight: 600;
    }

    QLabel#info_callout {
        color: #0369A1;
        background-color: #F0F9FF;
        border: 1px solid #BAE6FD;
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 9pt;
    }

    QLabel#status_label {
        color: #1E293B;
        font-size: 9.5pt;
        font-weight: 600;
    }

    QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {
        background-color: #FFFFFF;
        color: #1E293B;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 9.5pt;
        min-height: 20px;
    }

    QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {
        border: 1.5px solid #059669;
    }

    QComboBox::drop-down, QDateEdit::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 24px;
        border-left: 1px solid #CBD5E1;
        background-color: #F8FAFC;
    }

    QPushButton#btn_browse {
        background-color: #FFFFFF;
        color: #334155;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 600;
        font-size: 9pt;
    }
    QPushButton#btn_browse:hover {
        background-color: #F1F5F9;
        border-color: #94A3B8;
        color: #0F172A;
    }

    QPushButton#btn_download_action {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10B981, stop:1 #059669);
        color: #FFFFFF;
        border: 1px solid #047857;
        border-radius: 6px;
        padding: 8px 20px;
        font-size: 10pt;
        font-weight: 600;
    }
    QPushButton#btn_download_action:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34D399, stop:1 #10B981);
        border: 1px solid #059669;
    }
    QPushButton#btn_download_action:pressed {
        background: #047857;
    }
    QPushButton#btn_download_action:disabled {
        background: #E2E8F0;
        color: #94A3B8;
        border-color: #CBD5E1;
    }

    QPushButton#btn_cancel_action {
        background-color: #FFFFFF;
        color: #475569;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 8px 18px;
        font-size: 9.5pt;
        font-weight: 600;
    }
    QPushButton#btn_cancel_action:hover {
        background-color: #F1F5F9;
        border-color: #94A3B8;
        color: #0F172A;
    }

    QProgressBar {
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        background-color: #F1F5F9;
        height: 12px;
        text-align: center;
    }
    QProgressBar::chunk {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10B981);
        border-radius: 5px;
    }
"""


def _create_download_icon_pixmap() -> QIcon:
    """Ícono de descarga vectorial."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#FFFFFF"), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(16, 7, 16, 20)
    p.drawLine(11, 15, 16, 20)
    p.drawLine(21, 15, 16, 20)
    p.drawLine(8, 23, 8, 25)
    p.drawLine(8, 25, 24, 25)
    p.drawLine(24, 25, 24, 23)
    p.end()
    return QIcon(pix)


class HistoryDownloadWidget(QWidget):
    """Pestaña interna para configurar y ejecutar la descarga de mediciones históricas."""

    download_finished = Signal(dict)
    close_requested = Signal()

    def __init__(
        self,
        default_host: str = "127.0.0.1",
        default_port: int = 9001,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.host = default_host
        self.port = default_port
        self._worker: HistoryDownloadWorker | None = None

        self._build_ui()
        self.setStyleSheet(DOWNLOAD_WIDGET_STYLE)
        self._update_destination_ui()
        self._update_period_ui()

    def set_server_target(self, host: str, port: int) -> None:
        """Actualiza el servidor destino según el dispositivo activo."""
        self.host = host
        self.port = port
        self.server_info_label.setText(f"Servidor TES3600: {self.host}:{self.port}")

    def _build_ui(self) -> None:
        self.setObjectName("history_download_page")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("card_container")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(16)

        # 1. Encabezado
        header_layout = QVBoxLayout()
        header_layout.setSpacing(3)
        title_lbl = QLabel("Descargar mediciones históricas desde servidor")
        title_lbl.setObjectName("section_title")
        self.server_info_label = QLabel(f"Servidor TES3600: {self.host}:{self.port}")
        self.server_info_label.setObjectName("section_subtitle")
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(self.server_info_label)
        card_layout.addLayout(header_layout)

        # 2. Formulario principal
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 2.1 Período
        self.period_combo = QComboBox()
        for label, code in PERIOD_OPTIONS:
            self.period_combo.addItem(label, code)
        self.period_combo.currentIndexChanged.connect(self._update_period_ui)

        period_lbl = QLabel("Período:")
        period_lbl.setObjectName("form_label")
        form.addRow(period_lbl, self.period_combo)

        # 2.2 Controles de período personalizado
        self.custom_container = QWidget()
        custom_layout = QVBoxLayout(self.custom_container)
        custom_layout.setContentsMargins(0, 4, 0, 4)
        custom_layout.setSpacing(8)

        now = datetime.now()
        start_default = now - timedelta(hours=1)

        dt_row_layout = QHBoxLayout()
        dt_row_layout.setSpacing(10)

        # Inicio
        lbl_from = QLabel("Desde:")
        lbl_from.setObjectName("form_label")
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("dd-MM-yyyy")
        self.start_date_edit.setDate(QDate(start_default.year, start_default.month, start_default.day))

        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm:ss")
        self.start_time_edit.setTime(QTime(start_default.hour, start_default.minute, start_default.second))

        # Fin
        lbl_to = QLabel("Hasta:")
        lbl_to.setObjectName("form_label")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("dd-MM-yyyy")
        self.end_date_edit.setDate(QDate(now.year, now.month, now.day))

        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setDisplayFormat("HH:mm:ss")
        self.end_time_edit.setTime(QTime(now.hour, now.minute, now.second))

        dt_row_layout.addWidget(lbl_from)
        dt_row_layout.addWidget(self.start_date_edit)
        dt_row_layout.addWidget(self.start_time_edit)
        dt_row_layout.addSpacing(12)
        dt_row_layout.addWidget(lbl_to)
        dt_row_layout.addWidget(self.end_date_edit)
        dt_row_layout.addWidget(self.end_time_edit)
        dt_row_layout.addStretch()

        custom_layout.addLayout(dt_row_layout)

        retention_note = QLabel(
            "ℹ El servidor conserva un máximo de 30 días de mediciones."
        )
        retention_note.setObjectName("info_callout")
        custom_layout.addWidget(retention_note)

        form.addRow("", self.custom_container)

        # 2.3 Intervalo de muestreo de la descarga
        self.sample_interval_container = QWidget()
        sample_interval_layout = QHBoxLayout()
        sample_interval_layout.setContentsMargins(0, 4, 0, 4)
        sample_interval_layout.setSpacing(8)

        self.interval_minutes = QSpinBox()
        self.interval_minutes.setRange(0, 60)
        self.interval_minutes.setPrefix(" min ")
        self.interval_minutes.setValue(0)

        self.interval_seconds = QSpinBox()
        self.interval_seconds.setRange(0, 59)
        self.interval_seconds.setPrefix(" s ")
        self.interval_seconds.setValue(0)

        self.interval_milliseconds = QSpinBox()
        self.interval_milliseconds.setRange(0, 999)
        self.interval_milliseconds.setPrefix(" ms ")
        self.interval_milliseconds.setValue(500)

        sample_interval_layout.addWidget(self.interval_minutes)
        sample_interval_layout.addWidget(self.interval_seconds)
        sample_interval_layout.addWidget(self.interval_milliseconds)
        sample_interval_layout.addStretch()

        interval_container_layout = QVBoxLayout()
        interval_container_layout.setContentsMargins(0, 0, 0, 0)
        interval_container_layout.setSpacing(4)
        interval_container_layout.addLayout(sample_interval_layout)
        self.sample_interval_container.setLayout(interval_container_layout)

        interval_lbl = QLabel("Intervalo:")
        interval_lbl.setObjectName("form_label")
        form.addRow(interval_lbl, self.sample_interval_container)

        # 2.4 Nombre de la descarga / registro
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej.: Historial carga transformador")
        self.name_input.setText(f"Historial_{now.strftime('%d-%m-%Y_%H%M')}")

        name_lbl = QLabel("Nombre:")
        name_lbl.setObjectName("form_label")
        form.addRow(name_lbl, self.name_input)

        # 2.4 Destino de la descarga mediante menú selector
        self.destination_combo = QComboBox()
        self.destination_combo.addItem(DESTINATION_INTERNAL)
        self.destination_combo.addItem(DESTINATION_LOCAL)
        self.destination_combo.currentIndexChanged.connect(self._update_destination_ui)

        dest_lbl = QLabel("Destino:")
        dest_lbl.setObjectName("form_label")
        form.addRow(dest_lbl, self.destination_combo)

        # 2.5 Controles para archivo local
        self.local_file_container = QWidget()
        local_layout = QVBoxLayout(self.local_file_container)
        local_layout.setContentsMargins(0, 4, 0, 4)
        local_layout.setSpacing(8)

        format_layout = QHBoxLayout()
        format_lbl = QLabel("Formato:")
        format_lbl.setObjectName("form_label")
        self.format_combo = QComboBox()
        for fmt in EXPORT_FORMATS:
            self.format_combo.addItem(fmt)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        format_layout.addWidget(format_lbl)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        local_layout.addLayout(format_layout)

        path_layout = QHBoxLayout()
        path_lbl = QLabel("Ruta destino:")
        path_lbl.setObjectName("form_label")
        self.path_input = QLineEdit()
        self.path_input.setReadOnly(True)
        self.path_input.setPlaceholderText("Seleccioná la ubicación del archivo...")
        self.browse_button = QPushButton("Examinar...")
        self.browse_button.setObjectName("btn_browse")
        self.browse_button.clicked.connect(self._browse_save_path)

        path_layout.addWidget(path_lbl)
        path_layout.addWidget(self.path_input, 1)
        path_layout.addWidget(self.browse_button)
        local_layout.addLayout(path_layout)

        form.addRow("", self.local_file_container)

        card_layout.addLayout(form)

        # 3. Estado y barra de progreso indeterminada
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(6)
        self.status_label = QLabel("Listo para descargar.")
        self.status_label.setObjectName("status_label")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_bar)
        card_layout.addLayout(progress_layout)

        # 4. Botonera de acciones
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        actions_layout.addStretch()

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("btn_cancel_action")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        self.download_button = QPushButton(" Iniciar descarga")
        self.download_button.setObjectName("btn_download_action")
        self.download_button.setIcon(_create_download_icon_pixmap())
        self.download_button.setIconSize(QSize(16, 16))
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_button.clicked.connect(self._start_download)

        actions_layout.addWidget(self.cancel_button)
        actions_layout.addWidget(self.download_button)
        card_layout.addLayout(actions_layout)

        root_layout.addWidget(card)
        root_layout.addStretch()

    def _update_period_ui(self) -> None:
        """Muestra u oculta los campos de período personalizado."""
        is_custom = self.period_combo.currentData() == 0x0F
        self.custom_container.setVisible(is_custom)

    def _update_destination_ui(self) -> None:
        """Habilita la selección de ruta y formato al elegir descarga en archivo local."""
        is_local = self.destination_combo.currentText() == DESTINATION_LOCAL
        self.local_file_container.setVisible(is_local)

    def _on_format_changed(self) -> None:
        """Actualiza la extensión en la ruta si ya se seleccionó una."""
        current_path = self.path_input.text().strip()
        if not current_path:
            return
        selected_fmt = self.format_combo.currentText()
        extension, _ = EXPORT_FORMATS[selected_fmt]
        p = Path(current_path)
        new_path = str(p.with_suffix(f".{extension}"))
        self.path_input.setText(new_path)

    def _browse_save_path(self) -> None:
        """Abre el diálogo de guardado reutilizando los filtros de exportación."""
        selected_fmt = self.format_combo.currentText()
        extension, file_filter = EXPORT_FORMATS[selected_fmt]

        suggested_name = self.name_input.text().strip() or "registro_historico"
        safe_name = "".join(
            c if c.isalnum() or c in (" ", "-", "_") else "_" for c in suggested_name
        ).strip() or "registro_historico"

        filename = f"{safe_name}.{extension}"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Seleccionar destino del archivo",
            filename,
            file_filter,
        )
        if not path:
            return

        if not path.lower().endswith(f".{extension}"):
            path += f".{extension}"

        self.path_input.setText(path)

    def _get_sample_interval_ms(self) -> int:
        return (
            self.interval_minutes.value() * 60_000
            + self.interval_seconds.value() * 1_000
            + self.interval_milliseconds.value()
        )

    def _validate_inputs(self) -> bool:
        """Valida que los datos ingresados sean coherentes y cumplan las reglas."""
        interval_ms = self._get_sample_interval_ms()
        if not 500 <= interval_ms <= 3_600_000:
            QMessageBox.warning(
                self,
                "Intervalo inválido",
                "El intervalo de muestreo debe estar entre 500 ms y 1 hora. "
                "Para seleccionar 1 hora exacta, ingresá 60 minutos y dejá segundos y milisegundos en cero.",
            )
            self.interval_milliseconds.setFocus()
            return False

        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Nombre requerido", "Ingresá un nombre para la descarga.")
            self.name_input.setFocus()
            return False

        # Validación de destino local
        if self.destination_combo.currentText() == DESTINATION_LOCAL:
            path_str = self.path_input.text().strip()
            if not path_str:
                QMessageBox.warning(
                    self,
                    "Ruta requerida",
                    "Seleccioná la ruta y el nombre del archivo local mediante el botón Examinar.",
                )
                self.browse_button.setFocus()
                return False

        # Validación de período personalizado
        if self.period_combo.currentData() == 0x0F:
            s_date = self.start_date_edit.date()
            s_time = self.start_time_edit.time()
            start_dt = datetime(
                s_date.year(), s_date.month(), s_date.day(),
                s_time.hour(), s_time.minute(), s_time.second(),
            )

            e_date = self.end_date_edit.date()
            e_time = self.end_time_edit.time()
            end_dt = datetime(
                e_date.year(), e_date.month(), e_date.day(),
                e_time.hour(), e_time.minute(), e_time.second(),
            )

            now = datetime.now()

            if start_dt > end_dt:
                QMessageBox.warning(
                    self,
                    "Período inválido",
                    "La fecha y hora inicial no puede ser posterior a la fecha y hora final.",
                )
                return False

            if end_dt > now:
                QMessageBox.warning(
                    self,
                    "Fecha futura",
                    "La fecha y hora final no puede estar en el futuro respecto a la hora actual.",
                )
                return False

            retention_limit = now - timedelta(days=30)
            if start_dt < retention_limit:
                dias_antiguedad = (now - start_dt).days
                QMessageBox.warning(
                    self,
                    "Límite de retención superado",
                    f"La fecha inicial solicitada tiene {dias_antiguedad} días de antigüedad.\n\n"
                    "El servidor almacena un historial máximo de 30 días de mediciones.",
                )
                return False

            if (end_dt - start_dt).total_seconds() > 30 * 24 * 3600:
                QMessageBox.warning(
                    self,
                    "Rango demasiado extenso",
                    "El rango de fechas seleccionado supera los 30 días máximos admitidos.",
                )
                return False

        return True

    def _start_download(self) -> None:
        """Inicia la descarga en el hilo secundario."""
        if not self._validate_inputs():
            return

        name = self.name_input.text().strip()
        is_local = self.destination_combo.currentText() == DESTINATION_LOCAL
        destination_mode = "local_file" if is_local else "internal"

        export_path = Path(self.path_input.text().strip()) if is_local else None
        export_extension = None
        if is_local:
            selected_fmt = self.format_combo.currentText()
            export_extension = EXPORT_FORMATS[selected_fmt][0]

        is_custom = self.period_combo.currentData() == 0x0F
        period_code = self.period_combo.currentData() if not is_custom else None

        start_ms = None
        end_ms = None
        if is_custom:
            s_date = self.start_date_edit.date()
            s_time = self.start_time_edit.time()
            start_dt = datetime(
                s_date.year(), s_date.month(), s_date.day(),
                s_time.hour(), s_time.minute(), s_time.second(),
            )
            e_date = self.end_date_edit.date()
            e_time = self.end_time_edit.time()
            end_dt = datetime(
                e_date.year(), e_date.month(), e_date.day(),
                e_time.hour(), e_time.minute(), e_time.second(),
            )
            start_ms = int(start_dt.timestamp() * 1000)
            end_ms = int(end_dt.timestamp() * 1000)

        # Preparar UI para ejecución
        self._set_controls_enabled(False)
        self.progress_bar.setRange(0, 0)  # Barra de progreso indeterminada
        self.status_label.setText("Iniciando conexión con el servidor...")

        self._worker = HistoryDownloadWorker(
            host=self.host,
            port=self.port,
            request_mode="custom" if is_custom else "predefined",
            name=name,
            destination_mode=destination_mode,
            period_code=period_code,
            start_ms=start_ms,
            end_ms=end_ms,
            sample_interval_ms=self._get_sample_interval_ms(),
            export_path=export_path,
            export_extension=export_extension,
            parent=self,
        )

        self._worker.status_updated.connect(self._on_status_updated)
        self._worker.records_count_updated.connect(self._on_records_count_updated)
        self._worker.finished_successfully.connect(self._on_worker_finished)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.cancelled.connect(self._on_worker_cancelled)

        self._worker.start()

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Habilita o deshabilita controles durante la descarga."""
        self.period_combo.setEnabled(enabled)
        self.name_input.setEnabled(enabled)
        self.destination_combo.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)
        self.start_date_edit.setEnabled(enabled)
        self.start_time_edit.setEnabled(enabled)
        self.end_date_edit.setEnabled(enabled)
        self.end_time_edit.setEnabled(enabled)
        self.interval_minutes.setEnabled(enabled)
        self.interval_seconds.setEnabled(enabled)
        self.interval_milliseconds.setEnabled(enabled)
        self.download_button.setEnabled(enabled)

        if not enabled:
            self.cancel_button.setText("Detener")
        else:
            self.cancel_button.setText("Cancelar")

    def _on_status_updated(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_records_count_updated(self, count: int) -> None:
        pass

    def _on_worker_finished(self, result: dict) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self._set_controls_enabled(True)
        self._worker = None

        count = result.get("count", 0)
        if count == 0:
            QMessageBox.information(
                self,
                "Sin mediciones",
                "El servidor no dispone de registros para el período solicitado.",
            )
            return

        # Emitir resultado para que RecordingTab lo registre o guarde
        self.download_finished.emit(result)

    def _on_worker_error(self, error_message: str) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Error: {error_message}")
        self._set_controls_enabled(True)
        self._worker = None

        QMessageBox.critical(
            self,
            "Error en la descarga",
            f"No se pudo completar la descarga histórica:\n\n{error_message}",
        )

    def _on_worker_cancelled(self) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText("Operación cancelada por el usuario.")
        self._set_controls_enabled(True)
        self._worker = None

    def _on_cancel_clicked(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("Deteniendo descarga...")
            self._worker.cancel()
        else:
            self.close_requested.emit()
