"""Pruebas para el orden de exportación, tema claro de calendario y selección múltiple de destino."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QApplication

from app.tes3600.services.history_service import CANONICAL_HEADERS, order_headers_like_history
from app.ui.widgets.tes3600.history_download_widget import HistoryDownloadWidget
from app.ui.widgets.tes3600.recording_tab import Recording, RecordingTab


class TestRecordingOrderAndHistoryFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_canonical_headers_order(self):
        """Verifica que el orden canónico inicie con V1, I1, kVA1, kW1..."""
        self.assertEqual(CANONICAL_HEADERS[0], "V1")
        self.assertEqual(CANONICAL_HEADERS[1], "I1")
        self.assertIn("kVA1", CANONICAL_HEADERS)
        self.assertIn("kW1", CANONICAL_HEADERS)
        self.assertIn("V2", CANONICAL_HEADERS)
        self.assertIn("I2", CANONICAL_HEADERS)
        self.assertIn("V3", CANONICAL_HEADERS)
        self.assertIn("I3", CANONICAL_HEADERS)

    def test_order_headers_like_history(self):
        """Verifica que order_headers_like_history ordene cualquier subconjunto según el historial."""
        unordered = ["kW1", "I1", "V1", "kVAR1", "FP1", "custom_field"]
        ordered = order_headers_like_history(unordered)
        self.assertEqual(ordered, ["V1", "I1", "kW1", "FP1", "kVAR1", "custom_field"])

    def test_recording_tab_add_sample_dict_reordering(self):
        """Verifica que add_sample ordene los diccionarios según el estándar de history (V1 - I1 - ...)."""
        tab = RecordingTab()
        rec = Recording(
            record_id=1,
            name="Prueba Orden",
            started_at=datetime.now(),
            duration_seconds=60,
            sample_interval_seconds=1.0,
            status="Registrando",
        )
        tab._recordings[1] = rec

        # Diccionario con claves en orden desordenado (kW1 primero, V1 e I1 al final)
        values = {
            "kW1": 10.5,
            "kVAR1": 2.1,
            "FP1": 0.95,
            "V1": 220.3,
            "I1": 4.8,
            "Theta1": 18.2,
            "kVA1": 11.0,
        }

        success = tab.add_sample(1, datetime.now(), values)
        self.assertTrue(success)

        # Los encabezados deben haber sido guardados en el orden de history: V1, I1, kVA1, kW1, FP1, kVAR1, Theta1
        expected_headers = ["V1", "I1", "kVA1", "kW1", "FP1", "kVAR1", "Theta1"]
        self.assertEqual(rec.headers, expected_headers)

        # La muestra agregada debe tener los valores en ese mismo orden
        sample_row = rec.samples[0]
        # sample_row[0] es la estampa de tiempo
        self.assertEqual(sample_row[1], 220.3)  # V1
        self.assertEqual(sample_row[2], 4.8)    # I1
        self.assertEqual(sample_row[3], 11.0)   # kVA1
        self.assertEqual(sample_row[4], 10.5)   # kW1
        self.assertEqual(sample_row[5], 0.95)   # FP1
        self.assertEqual(sample_row[6], 2.1)    # kVAR1
        self.assertEqual(sample_row[7], 18.2)   # Theta1

    def test_recording_tab_export_coherence_with_history(self):
        """Verifica que al exportar a CSV, el orden de encabezados sea (V1 - I1 - ...)."""
        tab = RecordingTab()
        rec = Recording(
            record_id=1,
            name="Export Coherente",
            started_at=datetime(2026, 11, 24, 10, 0, 0),
            duration_seconds=60,
            sample_interval_seconds=1.0,
            status="Registrando",
        )
        tab._recordings[1] = rec
        tab.add_sample(1, datetime(2026, 11, 24, 10, 0, 0), {
            "kW1": 5.0,
            "V1": 230.0,
            "I1": 2.5,
        })
        # Forzar estado Finalizado tras agregar muestra
        rec.status = "Finalizado"

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test_order.csv"
            tab._write_recording_file(rec, csv_path, "csv")

            imported = tab._read_recording_file(csv_path, "csv")
            self.assertEqual(imported["headers"], ["V1", "I1", "kW1"])
            self.assertEqual(imported["samples"][0][1], "230.0")
            self.assertEqual(imported["samples"][0][2], "2.5")
            self.assertEqual(imported["samples"][0][3], "5.0")

    def test_history_download_widget_light_calendar_theme(self):
        """Verifica que el selector de fechas del apartado personalizado tenga tema light."""
        widget = HistoryDownloadWidget()

        # Selector 'Desde'
        cal_start = widget.start_date_edit.calendarWidget()
        self.assertIsNotNone(cal_start)
        style_start = cal_start.styleSheet()
        self.assertIn("#FFFFFF", style_start)
        self.assertIn("#F8FAFC", style_start)
        self.assertIn("#0284C7", style_start)

        # Selector 'Hasta'
        cal_end = widget.end_date_edit.calendarWidget()
        self.assertIsNotNone(cal_end)
        style_end = cal_end.styleSheet()
        self.assertIn("#FFFFFF", style_end)
        self.assertIn("#F8FAFC", style_end)
        self.assertIn("#0284C7", style_end)

    def test_history_download_widget_checkboxes_presence_and_defaults(self):
        """Verifica la presencia y estados por defecto de las casillas de selección de destino."""
        widget = HistoryDownloadWidget()

        self.assertTrue(hasattr(widget, "chk_internal"))
        self.assertTrue(hasattr(widget, "chk_file"))

        # Por defecto, registro local activo y archivo inactivo
        self.assertTrue(widget.chk_internal.isChecked())
        self.assertFalse(widget.chk_file.isChecked())
        self.assertTrue(widget.local_file_container.isHidden())

        # Al marcar archivo, se muestra el contenedor de ruta y formato
        widget.chk_file.setChecked(True)
        self.assertFalse(widget.local_file_container.isHidden())

        # Ambos pueden estar marcados a la vez
        self.assertTrue(widget.chk_internal.isChecked())
        self.assertTrue(widget.chk_file.isChecked())

    @patch("PySide6.QtWidgets.QMessageBox.warning")
    def test_history_download_widget_validation_both_unchecked(self, mock_warning):
        """Verifica que se requiera al menos un destino seleccionado."""
        widget = HistoryDownloadWidget()
        widget.chk_internal.setChecked(False)
        widget.chk_file.setChecked(False)

        self.assertFalse(widget._validate_inputs())
        mock_warning.assert_called()

    @patch("PySide6.QtWidgets.QMessageBox.information")
    def test_history_download_completed_both_destinations(self, mock_info):
        """Verifica que al seleccionar ambos destinos, se cree el registro interno y se guarde el archivo."""
        tab = RecordingTab()
        initial_count = len(tab._recordings)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "descarga_ambos.csv"
            samples = [
                ["2026-11-24 10:00:00.000", 220.0, 10.0, 2.2, 2.2],
            ]
            headers = ["V1", "I1", "kVA1", "kW1"]

            result = {
                "name": "Descarga Dual",
                "started_at": datetime(2026, 11, 24, 10, 0, 0),
                "duration_seconds": 1,
                "sample_interval_seconds": 0.5,
                "headers": headers,
                "samples": samples,
                "destination_mode": "both",
                "export_path": csv_path,
                "export_extension": "csv",
                "count": 1,
            }

            tab._on_history_download_completed(result)

            # 1. Se debe haber creado el registro interno en RecordingTab
            self.assertEqual(len(tab._recordings), initial_count + 1)
            new_rec = list(tab._recordings.values())[-1]
            self.assertEqual(new_rec.name, "Descarga Dual")
            self.assertEqual(new_rec.headers, headers)

            # 2. Se debe haber generado el archivo en la ruta especificada
            self.assertTrue(csv_path.exists())
            self.assertGreater(csv_path.stat().st_size, 0)

            # 3. El archivo exportado debe coincidir
            imported = tab._read_recording_file(csv_path, "csv")
            self.assertEqual(imported["headers"], headers)
            self.assertEqual(len(imported["samples"]), 1)


if __name__ == "__main__":
    unittest.main()
