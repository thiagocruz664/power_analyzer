import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication

from app.device_manager.device import Device
from app.ui.main_window import MainWindow
from app.ui.tool_discovery import ToolDiscoveryService
from app.ui.widgets.base_tool import DeviceToolWidget
from app.ui.widgets.tes3600.real_time_measurement import RealTimeMeasurementWidget
from app.ui.widgets.tes3600.recording_tab import RecordingTab


class TestToolDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_scenario_a_initial_state_no_device(self):
        """Escenario A: inicio sin dispositivo conectado."""
        window = MainWindow()

        # No debe haber herramientas específicas de ningún dispositivo en la barra lateral
        self.assertEqual(len(window.workspace_buttons), 0)
        # No se debe abrir ninguna herramienta por defecto
        self.assertEqual(window.tabs.count(), 0)
        # Estado de conexión desconectado
        self.assertIn("Desconectado", window.connection_status.text())
        self.assertIn("sin conectar", window.device_status.text())

    def test_scenario_b_tes3600_connection(self):
        """Escenario B: conexión al TES3600 y descubrimiento dinámico."""
        window = MainWindow()
        device = Device(name="TES3600 Principal", model="TES3600", connection_type="tcp")

        window._load_device_tools(device)

        # Se deben haber descubierto las 2 herramientas existentes
        self.assertIn("Medición en tiempo real", window.workspace_buttons)
        self.assertIn("Registro de mediciones", window.workspace_buttons)
        self.assertEqual(len(window.workspace_buttons), 2)

        # La primera herramienta descubierta debe abrirse como pestaña inicial
        self.assertEqual(window.tabs.count(), 1)
        self.assertEqual(window.tabs.tabText(0), "Medición en tiempo real")
        self.assertIsInstance(window.tabs.widget(0), RealTimeMeasurementWidget)

        # Abrir la segunda herramienta
        window._open_workspace("Registro de mediciones")
        self.assertEqual(window.tabs.count(), 2)
        self.assertEqual(window.tabs.tabText(1), "Registro de mediciones")
        self.assertIsInstance(window.tabs.widget(1), RecordingTab)

    def test_scenario_c_new_tool_discovery_without_modifying_mainwindow(self):
        """Escenario C: incorporación de una nueva herramienta sin tocar MainWindow."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            device_dir = tmp_path / "tes3600"
            device_dir.mkdir()

            # Crear una nueva herramienta arbitraria
            tool_code = """# Monitor de Armónicos
from app.ui.widgets.base_tool import DeviceToolWidget

class HarmonicAnalyzerWidget(DeviceToolWidget):
    pass
"""
            tool_file = device_dir / "custom_harmonics_tool.py"
            tool_file.write_text(tool_code, encoding="utf-8")

            discovery = ToolDiscoveryService(widgets_base_dir=tmp_path)
            device = Device(name="TES 3600", model="TES3600", connection_type="tcp")

            tools = discovery.discover_tools_for_device(device)
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0].display_name, "Monitor de Armónicos")

            instance = tools[0].create_instance()
            self.assertIsInstance(instance, DeviceToolWidget)

    def test_scenario_d_new_device_directory(self):
        """Escenario D: nuevo dispositivo y aislamiento de herramientas."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Directorio para dispositivo 'fluke435'
            fluke_dir = tmp_path / "fluke435"
            fluke_dir.mkdir()
            tool_fluke = fluke_dir / "fluke_monitor.py"
            tool_fluke.write_text("""# Analizador Fluke 435
from app.ui.widgets.base_tool import DeviceToolWidget

class FlukeMonitorWidget(DeviceToolWidget):
    pass
""", encoding="utf-8")

            # Directorio para TES3600
            tes_dir = tmp_path / "tes3600"
            tes_dir.mkdir()
            tool_tes = tes_dir / "tes_monitor.py"
            tool_tes.write_text("""# Analizador TES3600
from app.ui.widgets.base_tool import DeviceToolWidget

class TESMonitorWidget(DeviceToolWidget):
    pass
""", encoding="utf-8")

            discovery = ToolDiscoveryService(widgets_base_dir=tmp_path)

            # Descubrir para Fluke
            dev_fluke = Device(name="Fluke Equipo 1", model="Fluke435", connection_type="tcp")
            fluke_tools = discovery.discover_tools_for_device(dev_fluke)
            self.assertEqual(len(fluke_tools), 1)
            self.assertEqual(fluke_tools[0].display_name, "Analizador Fluke 435")

            # Descubrir para TES
            dev_tes = Device(name="TES Equipo 2", model="TES3600", connection_type="tcp")
            tes_tools = discovery.discover_tools_for_device(dev_tes)
            self.assertEqual(len(tes_tools), 1)
            self.assertEqual(tes_tools[0].display_name, "Analizador TES3600")

    def test_scenario_e_disconnection_and_reconnection(self):
        """Escenario E: desconexión retira herramientas y reconexión no duplica."""
        window = MainWindow()
        device = Device(name="TES3600 Lab", model="TES3600", connection_type="tcp")

        # Conectar
        window.active_device = device
        window._load_device_tools(device)
        self.assertEqual(len(window.workspace_buttons), 2)
        self.assertGreater(window.tabs.count(), 0)

        # Desconectar
        window._disconnect_device()
        self.assertEqual(len(window.workspace_buttons), 0)
        self.assertEqual(window.tabs.count(), 0)
        self.assertEqual(len(window._discovered_tools), 0)
        self.assertIsNone(window.active_device)

        # Reconectar
        window.active_device = device
        window._load_device_tools(device)
        self.assertEqual(len(window.workspace_buttons), 2)
        self.assertEqual(window.tabs.count(), 1)

        # Reconexión con el mismo dispositivo no duplica botones
        window._load_device_tools(device)
        self.assertEqual(len(window.workspace_buttons), 2)

    def test_scenario_f_incompatible_module_ignored(self):
        """Escenario F: archivos sin cabecera o sin clase compatible son omitidos sin fallar."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            device_dir = tmp_path / "tes3600"
            device_dir.mkdir()

            # 1. Archivo sin comentario de primera línea
            (device_dir / "helper.py").write_text("class Helper:\n    pass\n", encoding="utf-8")

            # 2. Archivo con cabecera pero sin clase DeviceToolWidget
            (device_dir / "invalid_widget.py").write_text("# Herramienta Invalida\nclass NotAWidget:\n    pass\n", encoding="utf-8")

            # 3. Archivo válido
            (device_dir / "valid_tool.py").write_text("""# Herramienta Válida
from app.ui.widgets.base_tool import DeviceToolWidget

class ValidWidget(DeviceToolWidget):
    pass
""", encoding="utf-8")

            discovery = ToolDiscoveryService(widgets_base_dir=tmp_path)
            device = Device(name="TES", model="TES3600", connection_type="tcp")

            tools = discovery.discover_tools_for_device(device)
            # Solo la válida debe ser descubierta
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0].display_name, "Herramienta Válida")

    def test_scenario_g_import_or_instantiation_error_handled(self):
        """Escenario G: error de importación o instanciación no detiene la aplicación."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            device_dir = tmp_path / "tes3600"
            device_dir.mkdir()

            # Módulo con error sintáctico
            (device_dir / "syntax_error_tool.py").write_text("# Herramienta Rota\ndef invalid syntax here!", encoding="utf-8")

            # Módulo válido
            (device_dir / "valid_tool.py").write_text("""# Herramienta Sana
from app.ui.widgets.base_tool import DeviceToolWidget

class HealthyWidget(DeviceToolWidget):
    pass
""", encoding="utf-8")

            discovery = ToolDiscoveryService(widgets_base_dir=tmp_path)
            device = Device(name="TES", model="TES3600", connection_type="tcp")

            tools = discovery.discover_tools_for_device(device)
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0].display_name, "Herramienta Sana")


if __name__ == "__main__":
    unittest.main()
