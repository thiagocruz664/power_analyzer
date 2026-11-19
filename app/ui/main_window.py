
import logging
import sys
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.tool_discovery import ToolDiscoveryService, DiscoveredTool
from app.ui.widgets.base_tool import DeviceToolWidget
from app.ui.widgets.tes3600.real_time_measurement import RealTimeMeasurementWidget
from app.ui.widgets.tes3600.recording_tab import RecordingTab
from app.ui.widgets.common.new_device_dialog import NewDeviceDialog
from PySide6.QtWidgets import QMessageBox
from app.device_manager.device import Device
from app.device_manager.device_repository import DeviceRepository

from app.ui.widgets.common.select_device_dialog import SelectDeviceDialog

from app.tes3600.services.measurement_service import TCPMeasurementService

logger = logging.getLogger("PowerAnalyzer.MainWindow")

def _ensure_tab_icons():
    """Asegura la existencia de los íconos para cerrar pestañas."""
    icons_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    close_png = icons_dir / "tab_close.png"
    hover_png = icons_dir / "tab_close_hover.png"

    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

    def _draw_icon(path, color, bg=None):
        size = 32
        cross_size = 21.0
        stroke = 3.8
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if bg:
            p.setBrush(QColor(bg))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
        pen = QPen(QColor(color))
        pen.setWidthF(stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        offset = (size - cross_size) / 2.0
        p.drawLine(offset, offset, size - offset, size - offset)
        p.drawLine(size - offset, offset, offset, size - offset)
        p.end()
        pix.save(str(path))

    _draw_icon(close_png, "#546678")
    _draw_icon(hover_png, "#E53E3E", "#FDE8E8")

    return close_png.as_posix(), hover_png.as_posix()


class DetachableTabBar(QTabBar):
    """Permite reordenar pestañas y desprender una pestaña al arrastrarla fuera de la barra."""

    detachRequested = Signal(str, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(True)
        self._drag_title = None
        self._drag_start = None
        self._detaching = False

    def mousePressEvent(self, event: QMouseEvent):
        self._drag_title = None
        self._drag_start = None
        self._detaching = False

        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            index = self.tabAt(pos)
            if index >= 0:
                # Si el clic es sobre el botón de cerrar, no iniciar lógica de desprendimiento
                close_btn = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
                if not (close_btn and close_btn.geometry().contains(pos)):
                    self._drag_title = self.tabText(index)
                    self._drag_start = pos

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)

        if (
            self._drag_title is None
            or self._drag_start is None
            or self._detaching
            or not (event.buttons() & Qt.MouseButton.LeftButton)
        ):
            return

        current = event.position().toPoint()

        # Umbral mínimo para evitar desprendimientos accidentales con clics rápidos
        if (current - self._drag_start).manhattanLength() < 12:
            return

        global_pos = event.globalPosition().toPoint()
        main_window = self.window()

        # Se desprende únicamente al arrastrar deliberadamente la pestaña FUERA de la barra:
        # - Hacia abajo (área del contenido / espacio de trabajo)
        # - Hacia arriba (fuera de la barra)
        # - Fuera de los extremos laterales
        # - Fuera de la ventana principal
        # Mientras el cursor permanezca dentro de la barra, el usuario puede reordenar
        # horizontalmente las pestañas con total libertad y fluidez.
        vertical_dist = abs(current.y() - self._drag_start.y())
        out_of_bar = (
            (current.y() > self.height() + 15 and vertical_dist > 20)
            or (current.y() < -15 and vertical_dist > 20)
            or current.x() < -20
            or current.x() > self.width() + 20
            or (main_window is not None and not main_window.frameGeometry().contains(global_pos))
        )

        if out_of_bar:
            self._detaching = True
            drag_title = self._drag_title
            self._drag_title = None
            self._drag_start = None
            if self.mouseGrabber() == self:
                self.releaseMouse()
            self.detachRequested.emit(drag_title, global_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        self._drag_title = None
        self._drag_start = None
        self._detaching = False


class DetachedWindow(QMainWindow):
    """Ventana independiente que permite devolver la pestaña al espacio principal."""

    def __init__(self, page, title, original_index, return_callback):
        super().__init__()

        self.page_title = title
        self.original_index = original_index
        self.return_callback = return_callback

        self.setWindowTitle(f"{title} - Power Analyzer")
        self.resize(1000, 700)
        self.setMinimumSize(700, 450)

        self.setCentralWidget(page)

    def closeEvent(self, event):
        page = self.takeCentralWidget()

        if page is not None:
            self.return_callback(
                page,
                self.page_title,
                self.original_index,
            )

        event.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Power Analyzer")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 650)

        self.detached_windows = {}
        self.device_repository = DeviceRepository()
        self.discovery_service = ToolDiscoveryService()
        self.active_device = None
        self.active_connection = None
        self.recording_widget = None
        self._discovered_tools: dict[str, DiscoveredTool] = {}
        self._current_loaded_device_id: str | None = None
        self._current_acquisition_status = "Sin datos"
        self._last_valid_frame_time = None

        self._create_menu_bar()
        self._create_ui()
        self._apply_styles()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("Archivo")
        file_menu.addAction("Nueva sesión")
        file_menu.addAction("Guardar registro")
        file_menu.addSeparator()
        file_menu.addAction("Salir", self.close)

        view_menu = menu_bar.addMenu("Ver")
        view_menu.addAction(
            "Medición en tiempo real",
            lambda: self._open_workspace("Medición en tiempo real"),
        )
        view_menu.addAction(
            "Registro",
            lambda: self._open_workspace("Registro"),
        )
        view_menu.addAction(
            "FFT",
            lambda: self._open_workspace("FFT"),
        )
        view_menu.addAction(
            "Análisis",
            lambda: self._open_workspace("Análisis"),
        )

        device_menu = menu_bar.addMenu("Dispositivos")
        device_menu.addAction(
            "Nuevo",
            self._open_new_device_dialog,
        )
        device_menu.addSeparator()
        device_menu.addAction(
            "Conectar",
            self._open_connect_device_dialog,
        )
        device_menu.addAction(
            "Desconectar",
            self._disconnect_device,
        )

        settings_menu = menu_bar.addMenu("Configuración")
        settings_menu.addAction("Conexión")
        settings_menu.addAction("Protocolo")
        settings_menu.addAction("Dispositivos")

        language_menu = menu_bar.addMenu("Lenguaje")
        language_menu.addAction("Español")
        language_menu.addAction("English")

        help_menu = menu_bar.addMenu("Ayuda")
        help_menu.addAction("Acerca de Power Analyzer")

    def _create_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Barra lateral izquierda
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(225)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        sidebar_layout.setSpacing(5)

        section_label = QLabel("ESPACIOS DE TRABAJO")
        section_label.setObjectName("section_label")
        sidebar_layout.addWidget(section_label)
        sidebar_layout.addSpacing(8)

        self.tools_layout = QVBoxLayout()
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_layout.setSpacing(5)
        sidebar_layout.addLayout(self.tools_layout)

        self.workspace_buttons = {}

        sidebar_layout.addStretch()

        # Estado resumido
        status_panel = QFrame()
        status_panel.setObjectName("status_panel")

        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(10, 10, 10, 10)
        status_layout.setSpacing(5)

        status_title = QLabel("ESTADO")
        status_title.setObjectName("section_label")
        status_layout.addWidget(status_title)

        self.connection_status = QLabel("●  Desconectado")
        self.connection_status.setObjectName("disconnected")
        status_layout.addWidget(self.connection_status)

        self.device_status = QLabel("Dispositivo: sin conectar")
        self.device_status.setObjectName("small_info")
        status_layout.addWidget(self.device_status)

        self.connection_info = QLabel("TCP: sin configurar")
        self.connection_info.setObjectName("small_info")
        status_layout.addWidget(self.connection_info)

        self.config_info = QLabel("Protocolo: predeterminado")
        self.config_info.setObjectName("small_info")
        status_layout.addWidget(self.config_info)

        sidebar_layout.addWidget(status_panel)
        root.addWidget(sidebar)

        separator = QFrame()
        separator.setObjectName("sidebar_separator")
        separator.setFixedWidth(1)
        root.addWidget(separator)

        # Área de trabajo delimitada por un marco fino.
        workspace_container = QWidget()
        workspace_container.setObjectName("workspace_container")

        workspace_layout = QVBoxLayout(workspace_container)
        workspace_layout.setContentsMargins(14, 14, 14, 14)
        workspace_layout.setSpacing(0)

        self.workspace_frame = QFrame()
        self.workspace_frame.setObjectName("workspace_frame")

        frame_layout = QVBoxLayout(self.workspace_frame)
        frame_layout.setContentsMargins(1, 1, 1, 1)
        frame_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("workspace_tabs")
        self.tabs.setDocumentMode(False)
        self.tabs.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        tab_bar = DetachableTabBar(self.tabs)
        self.tabs.setTabBar(tab_bar)
        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(True)

        tab_bar.detachRequested.connect(self._detach_workspace)
        self.tabs.tabCloseRequested.connect(self._close_workspace)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        frame_layout.addWidget(self.tabs)
        workspace_layout.addWidget(self.workspace_frame)

        root.addWidget(workspace_container, 1)

        self.statusBar().showMessage("Aplicación iniciada")


    def _add_tool_button(self, tool_name: str) -> None:
        """Agrega un botón para la herramienta a la barra lateral."""
        if tool_name in self.workspace_buttons:
            return
        button = QPushButton(tool_name)
        button.setObjectName("workspace_button")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setCheckable(True)
        button.clicked.connect(
            lambda checked=False, n=tool_name: self._open_workspace(n)
        )
        self.tools_layout.addWidget(button)
        self.workspace_buttons[tool_name] = button

    def _load_device_tools(self, device: Device | None) -> None:
        """Descubre e incorpora las herramientas del dispositivo a la interfaz."""
        if device is None:
            self._clear_device_tools()
            return

        if self._current_loaded_device_id == device.id:
            return

        self._clear_device_tools()
        self._current_loaded_device_id = device.id

        tools = self.discovery_service.discover_tools_for_device(device)
        self._discovered_tools = {tool.display_name: tool for tool in tools}

        for tool in tools:
            self._add_tool_button(tool.display_name)

        # Si se descubrieron herramientas y no hay pestañas abiertas, abrir la primera
        if tools and self.tabs.count() == 0:
            first_tool_name = tools[0].display_name
            self._open_workspace(first_tool_name)

    def _clear_device_tools(self) -> None:
        """Elimina las herramientas y vistas del dispositivo activo."""
        tool_names = set(self._discovered_tools.keys())

        # Cerrar ventanas desprendidas que pertenezcan a herramientas del dispositivo
        for page, detached in list(self.detached_windows.items()):
            if detached.page_title in tool_names or isinstance(page, DeviceToolWidget):
                if hasattr(page, "on_device_disconnected"):
                    try:
                        page.on_device_disconnected()
                    except Exception as exc:
                        logger.error("Error al notificar desconexión a %s: %s", page, exc)
                detached.close()
                self.detached_windows.pop(page, None)

        # Cerrar pestañas de herramientas del dispositivo
        for idx in reversed(range(self.tabs.count())):
            page = self.tabs.widget(idx)
            title = self.tabs.tabText(idx)
            if title in tool_names or isinstance(page, DeviceToolWidget):
                if hasattr(page, "on_device_disconnected"):
                    try:
                        page.on_device_disconnected()
                    except Exception as exc:
                        logger.error("Error al notificar desconexión a %s: %s", page, exc)
                self.tabs.removeTab(idx)
                if page is not None:
                    page.deleteLater()

        # Eliminar botones de la barra lateral
        for button in self.workspace_buttons.values():
            self.tools_layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        self.workspace_buttons.clear()

        # Limpiar referencias
        self._discovered_tools.clear()
        self._current_loaded_device_id = None
        self.recording_widget = None

        if self.tabs.count() == 0:
            self.statusBar().showMessage("Sin espacios de trabajo abiertos")
        else:
            current_name = self.tabs.tabText(self.tabs.currentIndex())
            self._update_sidebar_selection(current_name)

    def _create_workspace_page(self, name: str) -> QWidget | None:
        # 1. Herramienta descubierta dinámicamente
        if name in self._discovered_tools:
            tool = self._discovered_tools[name]
            try:
                widget = tool.create_instance()
                if isinstance(widget, RecordingTab):
                    self.recording_widget = widget
                if hasattr(widget, "on_device_connected") and self.active_device is not None:
                    widget.on_device_connected(self.active_device, self.active_connection)
                if hasattr(widget, "on_acquisition_status_changed") and self.active_connection is not None:
                    widget.on_acquisition_status_changed(self._current_acquisition_status)
                if hasattr(widget, "on_valid_frame_received") and self._last_valid_frame_time is not None:
                    widget.on_valid_frame_received(self._last_valid_frame_time)
                return widget
            except Exception as exc:
                logger.error("Error al instanciar herramienta '%s': %s", name, exc, exc_info=True)
                QMessageBox.warning(
                    self,
                    "Error al abrir herramienta",
                    f"No se pudo inicializar la herramienta «{name}»:\n{exc}",
                )
                return None

        # 2. Compatibilidad con nombres predeterminados si no fueron descubiertos
        if name == "Medición en tiempo real":
            widget = RealTimeMeasurementWidget()
            if self.active_connection is not None:
                widget.set_acquisition_status(self._current_acquisition_status)
                if self._last_valid_frame_time is not None:
                    widget.set_last_valid_frame_time(self._last_valid_frame_time)
            return widget

        if name == "Registro":
            self.recording_widget = RecordingTab()
            return self.recording_widget

        # 3. Espacios de trabajo genéricos
        page = QWidget()
        page.setObjectName("workspace_page")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title = QLabel(name)
        title.setObjectName("page_title")

        descriptions = {
            "FFT": (
                "Análisis espectral y visualización de "
                "componentes frecuenciales."
            ),
            "Análisis": (
                "Herramientas de análisis de las mediciones adquiridas."
            ),
        }

        description = QLabel(
            descriptions.get(name, "Espacio de trabajo.")
        )
        description.setObjectName("page_description")
        description.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch()

        return page

    def _open_workspace(self, name: str) -> None:
        # Si ya está abierta como ventana desprendida, traerla al frente
        for page, detached in self.detached_windows.items():
            if detached.page_title == name:
                detached.raise_()
                detached.activateWindow()
                self._update_sidebar_selection(name)
                return

        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                self.tabs.setCurrentIndex(index)
                self._update_sidebar_selection(name)
                return

        page = self._create_workspace_page(name)
        if page is None:
            return

        index = self.tabs.addTab(page, name)
        self.tabs.setCurrentIndex(index)

        self._update_sidebar_selection(name)
        self.statusBar().showMessage(f"Espacio de trabajo: {name}")

    def _close_workspace(self, index):
        if 0 <= index < self.tabs.count():
            page = self.tabs.widget(index)
            self.tabs.removeTab(index)
            if page is not None:
                page.deleteLater()

        if self.tabs.count() == 0:
            self.statusBar().showMessage("Sin espacios de trabajo abiertos")
            for button in self.workspace_buttons.values():
                button.setChecked(False)
            return

        current_name = self.tabs.tabText(self.tabs.currentIndex())
        self._update_sidebar_selection(current_name)

    def _on_tab_changed(self, index):
        if 0 <= index < self.tabs.count():
            current_name = self.tabs.tabText(index)
            self._update_sidebar_selection(current_name)
            self.statusBar().showMessage(f"Espacio de trabajo: {current_name}")

    def _detach_workspace(self, title, global_pos):
        # Encontrar la pestaña por nombre, ya que pudo reordenarse durante el arrastre.
        index = -1

        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == title:
                index = i
                break

        if index < 0:
            return

        page = self.tabs.widget(index)
        original_index = index

        self.tabs.removeTab(index)
        page.setParent(None)

        detached = DetachedWindow(
            page,
            title,
            original_index,
            self._restore_workspace,
        )

        self.detached_windows[page] = detached
        detached.move(global_pos - QPoint(120, 15))
        detached.show()
        detached.raise_()
        detached.activateWindow()

        if self.tabs.count() > 0:
            self._update_sidebar_selection(
                self.tabs.tabText(self.tabs.currentIndex())
            )
        else:
            for button in self.workspace_buttons.values():
                button.setChecked(False)

        self.statusBar().showMessage(f"Ventana independiente: {title}")

    def _restore_workspace(self, page, title, original_index):
        self.detached_windows.pop(page, None)

        index = max(0, min(original_index, self.tabs.count()))
        self.tabs.insertTab(index, page, title)
        self.tabs.setCurrentWidget(page)

        self._update_sidebar_selection(title)
        self.statusBar().showMessage(f"Pestaña restaurada: {title}")

    def _update_sidebar_selection(self, active_name):
        for name, button in self.workspace_buttons.items():
            button.setChecked(name == active_name)

    def _open_new_device_dialog(self):
        dialog = NewDeviceDialog(self)

        if not dialog.exec():
            return

        try:
            config = dialog.get_device_config()
            device = Device(**config)

            self.device_repository.add(device)

            QMessageBox.information(
                self,
                "Dispositivo guardado",
                f"Se registró el dispositivo «{device.name}».",
            )

        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(
                self,
                "No se pudo guardar",
                str(exc),
            )

    
    def _open_connect_device_dialog(self):
        if self.active_connection is not None:
            QMessageBox.warning(
                self,
                "Conexión activa",
                "Desconectá el dispositivo actual antes de conectar otro.",
            )
            return

        try:
            devices = self.device_repository.get_all()
        except RuntimeError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if not devices:
            QMessageBox.information(
                self,
                "Sin dispositivos",
                "Primero registrá un dispositivo desde "
                "Dispositivos → Nuevo.",
            )
            return

        dialog = SelectDeviceDialog(devices, self)

        if not dialog.exec():
            return

        device = self.device_repository.get_by_id(
            dialog.selected_device_id()
        )

        if device is None:
            QMessageBox.warning(
                self,
                "Dispositivo no encontrado",
                "El dispositivo seleccionado ya no está registrado.",
            )
            return

        if device.connection_type != "tcp":
            QMessageBox.information(
                self,
                "Adquisición no disponible",
                "La adquisición por puerto serie todavía no está "
                "implementada. Seleccioná un dispositivo TCP.",
            )
            return

        self.active_device = device
        self.connection_status.setText("●  Conectando...")
        self.connection_info.setText(
            f"TCP: {device.host}:{device.port}"
        )
        self.device_status.setText(f"Dispositivo: {device.name}")
        self.statusBar().showMessage(
            f"Conectando con {device.name}..."
        )

        service = TCPMeasurementService(device, self)
        self.active_connection = service

        service.connected.connect(self._on_tcp_connected)
        service.measurements_received.connect(
            self._on_measurements_received
        )
        service.valid_frame_received.connect(
            self._on_valid_frame_received
        )
        service.status_changed.connect(
            self._on_acquisition_status_changed
        )
        service.error_occurred.connect(self._on_tcp_error)
        service.log_message.connect(self.statusBar().showMessage)
        service.finished.connect(
            lambda worker=service: self._on_tcp_service_finished(worker)
        )

        service.start()


    def _get_active_tool_widgets(self) -> list[QWidget]:
        """Obtiene todas las vistas activas tanto en pestañas como en ventanas desprendidas."""
        widgets: list[QWidget] = []
        for index in range(self.tabs.count()):
            w = self.tabs.widget(index)
            if w is not None and w not in widgets:
                widgets.append(w)
        for w in self.detached_windows:
            if w is not None and w not in widgets:
                widgets.append(w)
        return widgets


    def _get_real_time_widget(self):
        """Busca la vista de mediciones, incluso si está desprendida."""
        for widget in self._get_active_tool_widgets():
            if isinstance(widget, RealTimeMeasurementWidget):
                return widget
        return None


    def _get_recording_widget(self):
        for widget in self._get_active_tool_widgets():
            if isinstance(widget, RecordingTab):
                return widget
        return None
    

    def _forward_measurements_to_recording(self, measurements):
        widget = self._get_recording_widget()

        if widget is None or hasattr(widget, "on_measurements_received"):
            return

        timestamp = datetime.now()

        for record_id in widget.active_recording_ids():
            widget.add_sample(
                record_id=record_id,
                timestamp=timestamp,
                values=measurements,
                headers=list(measurements.keys()),
            )


    def _on_tcp_connected(self):
        self._current_acquisition_status = "Sin datos"
        self._last_valid_frame_time = None
        self.connection_status.setText("●  Conectado")
        self.connection_status.setStyleSheet("color: #247A46;")
        self.statusBar().showMessage("Conexión TCP establecida")
        self._load_device_tools(self.active_device)


    def _on_measurements_received(self, measurements):
        for widget in self._get_active_tool_widgets():
            if hasattr(widget, "on_measurements_received"):
                try:
                    widget.on_measurements_received(measurements)
                except Exception as exc:
                    logger.error("Error en on_measurements_received de %s: %s", widget, exc)
            elif isinstance(widget, RealTimeMeasurementWidget):
                widget.update_measurements(measurements)

        self._forward_measurements_to_recording(measurements)


    def _on_valid_frame_received(self, timestamp):
        self._last_valid_frame_time = timestamp
        for widget in self._get_active_tool_widgets():
            if hasattr(widget, "on_valid_frame_received"):
                try:
                    widget.on_valid_frame_received(timestamp)
                except Exception as exc:
                    logger.error("Error en on_valid_frame_received de %s: %s", widget, exc)
            elif isinstance(widget, RealTimeMeasurementWidget):
                widget.set_last_valid_frame_time(timestamp)


    def _on_acquisition_status_changed(self, status):
        self._current_acquisition_status = status
        for widget in self._get_active_tool_widgets():
            if hasattr(widget, "on_acquisition_status_changed"):
                try:
                    widget.on_acquisition_status_changed(status)
                except Exception as exc:
                    logger.error("Error en on_acquisition_status_changed de %s: %s", widget, exc)
            elif isinstance(widget, RealTimeMeasurementWidget):
                widget.set_acquisition_status(status)

        if status == "Recibiendo":
            self.connection_status.setText("●  Recibiendo datos")
            self.connection_status.setStyleSheet("color: #247A46;")
        elif status == "Sin señal":
            self.connection_status.setText("●  Sin señal")
            self.connection_status.setStyleSheet("color: #B33A3A;")
        elif status == "Sin datos":
            self.connection_status.setText("●  Conectado")
            self.connection_status.setStyleSheet("color: #247A46;")


    def _on_tcp_error(self, message):
        QMessageBox.warning(
            self,
            "Error de adquisición TCP",
            message,
        )


    def _on_tcp_service_finished(self, service):
        # No borrar una conexión nueva por una señal tardía de otra.
        if self.active_connection is not service:
            return

        self.active_connection = None
        self.active_device = None
        self._current_acquisition_status = "Sin datos"
        self._last_valid_frame_time = None

        self._clear_device_tools()

        self.connection_status.setText("●  Desconectado")
        self.connection_status.setStyleSheet("color: #A63838;")
        self.device_status.setText("Dispositivo: sin conectar")
        self.connection_info.setText("TCP: sin configurar")

        self.statusBar().showMessage("Conexión TCP finalizada")


    def _disconnect_device(self):
        service = self.active_connection

        if service is None and self.active_device is None:
            QMessageBox.information(
                self,
                "Sin conexión",
                "No hay ningún dispositivo conectado.",
            )
            return

        if isinstance(service, TCPMeasurementService):
            service.stop()

            if not service.wait(4000):
                QMessageBox.warning(
                    self,
                    "Desconexión pendiente",
                    "El hilo de adquisición todavía no terminó. "
                    "La conexión se mantiene referenciada para evitar "
                    "dejar un hilo activo sin control.",
                )
                return

        self.active_connection = None
        self.active_device = None

        self._clear_device_tools()

        self.connection_status.setText("●  Desconectado")
        self.connection_status.setStyleSheet("color: #A63838;")
        self.device_status.setText("Dispositivo: sin conectar")
        self.connection_info.setText("TCP: sin configurar")

        self.statusBar().showMessage("Dispositivo desconectado")


    def _apply_styles(self):
        close_icon, close_hover_icon = _ensure_tab_icons()

        style = """
            QMainWindow, QWidget#central {
                background-color: #F0F2F5;
                color: #253342;
            }

            QWidget {
                font-family: "Segoe UI";
                font-size: 10pt;
                color: #253342;
            }

            QMenuBar {
                background-color: #FFFFFF;
                color: #253342;
                border-bottom: 1px solid #CCD4DC;
                padding: 4px;
            }

            QMenuBar::item {
                color: #253342;
                background-color: transparent;
                padding: 7px 11px;
                border-radius: 3px;
            }

            QMenuBar::item:selected {
                color: #172A39;
                background-color: #E5EBF0;
            }

            QMenu {
                background-color: #FFFFFF;
                color: #253342;
                border: 1px solid #CCD4DC;
                padding: 4px;
            }

            QMenu::item {
                color: #253342;
                background-color: transparent;
                padding: 7px 24px;
            }

            QMenu::item:selected {
                color: #172A39;
                background-color: #E5EBF0;
            }

            #sidebar {
                background-color: #FFFFFF;
            }

            #sidebar_separator {
                background-color: #CCD4DC;
            }

            #section_label {
                color: #596A79;
                font-size: 8pt;
                font-weight: 700;
            }

            #workspace_button {
                color: #354757;
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                text-align: left;
                padding: 10px 9px;
            }

            #workspace_button:hover {
                color: #203849;
                background-color: #EDF1F5;
            }

            #workspace_button:checked {
                color: #183F58;
                background-color: #DCEAF3;
                border: 1px solid #C4D8E6;
                border-left: 3px solid #367BA2;
                padding-left: 7px;
                font-weight: 600;
            }

            #status_panel {
                background-color: #F6F8FA;
                border: 1px solid #D5DDE4;
                border-radius: 5px;
            }

            #disconnected {
                color: #A63838;
                font-size: 9pt;
                font-weight: 600;
            }

            #small_info {
                color: #4E6070;
                font-size: 8pt;
            }

            #workspace_container {
                background-color: #F0F2F5;
            }

            #workspace_frame {
                background-color: #FFFFFF;
                border: 1px solid #CCD4DC;
                border-radius: 4px;
            }

            #workspace_tabs {
                background-color: #E2E6EA;
                color: #253342;
                border: none;
            }

            QTabWidget::pane {
                background-color: #FFFFFF;
                border: none;
                border-top: 1px solid #CCD4DC;
                top: -1px;
            }

            QTabBar {
                background-color: #E2E6EA;
                qproperty-drawBase: false;
            }

            QTabBar::tab {
                background-color: #E2E6EA;
                color: #4A5D6E;
                padding: 7px 10px 7px 14px;
                margin-right: 2px;
                border: none;
                border-right: 1px solid #CCD4DC;
                border-bottom: 1px solid #CCD4DC;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }

            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #172A39;
                border-bottom: 1px solid #FFFFFF;
                font-weight: 600;
            }

            QTabBar::tab:hover:!selected {
                background-color: #D5DCE2;
                color: #1B2E3D;
            }

            QTabBar::close-button {
                image: url("__CLOSE_ICON__");
                subcontrol-origin: padding;
                subcontrol-position: right;
                right: 4px;
            }

            QTabBar::close-button:hover {
                image: url("__CLOSE_HOVER_ICON__");
            }

            #workspace_page {
                background-color: #FFFFFF;
                color: #253342;
            }

            #page_title {
                color: #203849;
                font-size: 19pt;
                font-weight: 600;
            }

            #page_description {
                color: #536575;
                font-size: 10pt;
            }

            QStatusBar {
                background-color: #FFFFFF;
                color: #465867;
                border-top: 1px solid #CCD4DC;
                font-size: 8pt;
            }

            QStatusBar::item {
                border: none;
            }

            QToolTip {
                background-color: #FFFFFF;
                color: #253342;
                border: 1px solid #BCC7D1;
                padding: 4px;
            }
            
            /* Diálogo: nuevo dispositivo */
            QDialog {
                background-color: #F0F2F5;
                color: #253342;
            }

            QDialog QLabel {
                color: #354757;
            }

            QDialog QGroupBox {
                background-color: #FFFFFF;
                color: #203849;
                border: 1px solid #CCD4DC;
                border-radius: 5px;
                margin-top: 12px;
                padding: 12px;
                font-weight: 600;
            }

            QDialog QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px;
                background-color: #F0F2F5;
            }

            QDialog QLineEdit,
            QDialog QComboBox,
            QDialog QSpinBox {
                background-color: #FFFFFF;
                color: #253342;
                border: 1px solid #BCC7D1;
                border-radius: 4px;
                padding: 6px 8px;
                selection-background-color: #DCEAF3;
                selection-color: #183F58;
            }

            QDialog QLineEdit:focus,
            QDialog QComboBox:focus,
            QDialog QSpinBox:focus {
                border: 1px solid #367BA2;
            }

            QDialog QLineEdit:disabled,
            QDialog QComboBox:disabled,
            QDialog QSpinBox:disabled {
                background-color: #E8ECEF;
                color: #8996A1;
                border-color: #D5DDE4;
            }

            QDialog QComboBox::drop-down {
                border: none;
                width: 24px;
            }

            QDialog QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                color: #253342;
                border: 1px solid #CCD4DC;
                selection-background-color: #DCEAF3;
                selection-color: #183F58;
                outline: none;
            }

            QDialog QRadioButton {
                color: #354757;
                spacing: 7px;
            }

            QDialog QRadioButton::indicator {
                width: 15px;
                height: 15px;
            }

            QDialog QRadioButton::indicator:checked {
                background-color: #367BA2;
                border: 2px solid #367BA2;
                border-radius: 8px;
            }

            QDialog QRadioButton::indicator:unchecked {
                background-color: #FFFFFF;
                border: 1px solid #9AAAB7;
                border-radius: 8px;
            }

            QDialog QDialogButtonBox QPushButton {
                background-color: #FFFFFF;
                color: #354757;
                border: 1px solid #BCC7D1;
                border-radius: 4px;
                padding: 7px 16px;
                min-width: 75px;
            }

            QDialog QDialogButtonBox QPushButton:hover {
                background-color: #E5EBF0;
                color: #203849;
                border-color: #AABAC7;
            }

            QDialog QDialogButtonBox QPushButton:default {
                background-color: #367BA2;
                color: #FFFFFF;
                border: 1px solid #2E6A8B;
                font-weight: 600;
            }

            QDialog QDialogButtonBox QPushButton:default:hover {
                background-color: #2E6A8B;
            }

            QDialog QDialogButtonBox QPushButton:pressed {
                background-color: #D5DCE2;
                color: #203849;
            }
        """

        self.setStyleSheet(
            style.replace("__CLOSE_ICON__", close_icon).replace(
                "__CLOSE_HOVER_ICON__", close_hover_icon
            )
        )


    def closeEvent(self, event):
        service = self.active_connection

        if isinstance(service, TCPMeasurementService):
            service.stop()

            if not service.wait(4000):
                QMessageBox.warning(
                    self,
                    "Cierre pendiente",
                    "La adquisición TCP todavía está finalizando. "
                    "Volvé a cerrar la aplicación cuando termine.",
                )
                event.ignore()
                return

            self.active_connection = None
            self.active_device = None

        for window in list(self.detached_windows.values()):
            window.close()

        event.accept()

