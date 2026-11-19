import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader
from openpyxl import load_workbook

from app.ui.widgets.tes3600.recording_tab import (
    Recording,
    RecordingTab,
    RecordingPreviewWindow,
    ImportRecordingDetailsDialog,
    format_timestamp_display,
    parse_timestamp,
    normalize_to_iso_timestamp,
)


class TestDateFormatAndExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_format_timestamp_display(self):
        # Datetime with milliseconds
        dt = datetime(2026, 10, 27, 17, 48, 58, 123000)
        self.assertEqual(format_timestamp_display(dt), "27-10-2026 17:48:58.123")

        # Datetime without milliseconds
        dt_no_ms = datetime(2026, 10, 27, 17, 48, 58)
        self.assertEqual(format_timestamp_display(dt_no_ms), "27-10-2026 17:48:58")

        # ISO string with space and milliseconds
        iso_str = "2026-10-27 17:48:58.123"
        self.assertEqual(format_timestamp_display(iso_str), "27-10-2026 17:48:58.123")

        # ISO string with 'T' separator
        iso_t = "2026-10-27T17:48:58.123"
        self.assertEqual(format_timestamp_display(iso_t), "27-10-2026 17:48:58.123")

        # Date only
        date_only = "2026-10-27"
        self.assertEqual(format_timestamp_display(date_only), "27-10-2026")

        # Already formatted DD-MM-YYYY
        dmy_str = "27-10-2026 17:48:58.123"
        self.assertEqual(format_timestamp_display(dmy_str), "27-10-2026 17:48:58.123")

    def test_parse_timestamp(self):
        # Parse ISO string
        dt1 = parse_timestamp("2026-10-27 17:48:58.123000")
        self.assertEqual(dt1, datetime(2026, 10, 27, 17, 48, 58, 123000))

        # Parse DD-MM-YYYY string with milliseconds
        dt2 = parse_timestamp("27-10-2026 17:48:58.123000")
        self.assertEqual(dt2, datetime(2026, 10, 27, 17, 48, 58, 123000))

        # Parse DD-MM-YYYY with seconds
        dt3 = parse_timestamp("27-10-2026 17:48:58")
        self.assertEqual(dt3, datetime(2026, 10, 27, 17, 48, 58))

        # Parse date only
        dt4 = parse_timestamp("27-10-2026")
        self.assertEqual(dt4, datetime(2026, 10, 27, 0, 0))

    def test_normalize_to_iso_timestamp(self):
        # Normalize DD-MM-YYYY
        self.assertEqual(
            normalize_to_iso_timestamp("27-10-2026 17:48:58.123"),
            "2026-10-27 17:48:58.123",
        )
        self.assertEqual(
            normalize_to_iso_timestamp("27-10-2026"),
            "2026-10-27",
        )
        # Already ISO
        self.assertEqual(
            normalize_to_iso_timestamp("2026-10-27 17:48:58.123"),
            "2026-10-27 17:48:58.123",
        )

    def test_recording_tab_table_date_display(self):
        tab = RecordingTab()
        rec = Recording(
            record_id=1,
            name="Prueba",
            started_at=datetime(2026, 10, 27, 14, 30, 0),
            duration_seconds=60,
            sample_interval_seconds=1.0,
            status="Finalizado",
        )
        tab._recordings[1] = rec
        tab._refresh_table()

        # Check item text in table column 0
        date_item = tab.table.item(0, 0)
        self.assertIsNotNone(date_item)
        self.assertEqual(date_item.text(), "27-10-2026 14:30:00")

    def test_preview_window_date_display(self):
        rec = Recording(
            record_id=1,
            name="Prueba Preview",
            started_at=datetime(2026, 10, 27, 14, 30, 0),
            duration_seconds=60,
            sample_interval_seconds=0.5,
            status="Finalizado",
            headers=["V1", "I1"],
            samples=[
                ["2026-10-27 14:30:00.000", "220.1", "5.0"],
                ["2026-10-27 14:30:00.500", "220.3", "5.1"],
            ],
        )
        win = RecordingPreviewWindow(rec)
        win.refresh()

        self.assertEqual(win.table.rowCount(), 2)
        # Column 0 is "Estampa de tiempo" and should be formatted DD-MM-AAAA
        self.assertEqual(win.table.item(0, 0).text(), "27-10-2026 14:30:00.000")
        self.assertEqual(win.table.item(1, 0).text(), "27-10-2026 14:30:00.500")

    def test_import_dialog_theme_and_format(self):
        default_dt = datetime(2026, 10, 27, 15, 45, 30)
        dialog = ImportRecordingDetailsDialog("Registro_Test", default_datetime=default_dt)

        # Date format must be dd-MM-yyyy
        self.assertEqual(dialog.date_input.displayFormat(), "dd-MM-yyyy")
        self.assertEqual(dialog.date_input.date(), QDate(2026, 10, 27))
        self.assertEqual(dialog.time_input.time(), QTime(15, 45, 30))

        # Check dialog style is light
        style = dialog.styleSheet()
        self.assertIn("#F8FAFC", style)
        self.assertIn("#FFFFFF", style)
        self.assertIn("#1E293B", style)

        # Check calendar widget styling
        cal = dialog.date_input.calendarWidget()
        self.assertIsNotNone(cal)
        cal_style = cal.styleSheet()
        self.assertIn("#FFFFFF", cal_style)
        self.assertIn("#F8FAFC", cal_style)

        # Grab calendar offscreen and verify light background (not dark #2d2d2d)
        cal.show()
        cal.resize(320, 260)
        pix = cal.grab()
        img = pix.toImage()
        center_color = img.pixelColor(img.width() // 2, img.height() // 2)
        # Background is white (#ffffff)
        self.assertEqual(center_color.name(), "#ffffff")

    def test_export_and_import_roundtrip(self):
        started = datetime(2026, 10, 27, 10, 0, 0)
        samples = [
            ["2026-10-27 10:00:00.000", "220.0", "10.0"],
            ["2026-10-27 10:00:00.500", "220.1", "10.1"],
            ["2026-10-27 10:00:01.000", "220.2", "10.2"],
        ]
        recording = Recording(
            record_id=1,
            name="Test Roundtrip",
            started_at=started,
            duration_seconds=10,
            sample_interval_seconds=0.5,
            status="Finalizado",
            headers=["V1", "I1"],
            samples=samples,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            for ext in ["csv", "txt", "xlsx", "pdf"]:
                file_path = tmp_path / f"export_test.{ext}"
                RecordingTab._write_recording_file(recording, file_path, ext)
                self.assertTrue(file_path.exists())

                # Check DD-MM-AAAA inside exported files
                if ext == "csv":
                    content = file_path.read_text(encoding="utf-8-sig")
                    self.assertIn("27-10-2026 10:00:00.000", content)
                    self.assertNotIn("2026-10-27 10:00:00.000", content)
                elif ext == "txt":
                    content = file_path.read_text(encoding="utf-8")
                    self.assertIn("27-10-2026 10:00:00.000", content)
                    self.assertNotIn("2026-10-27 10:00:00.000", content)
                elif ext == "xlsx":
                    wb = load_workbook(file_path)
                    sheet = wb.active
                    # Row 5 (index 4) is first sample
                    cell_val = str(sheet.cell(row=5, column=1).value)
                    self.assertEqual(cell_val, "27-10-2026 10:00:00.000")
                    wb.close()
                elif ext == "pdf":
                    reader = PdfReader(str(file_path))
                    pdf_text = reader.pages[0].extract_text()
                    self.assertIn("27-10-2026 10:00:00", pdf_text)

                # Now test reading the file back (import)
                imported = RecordingTab._read_recording_file(file_path, ext)
                self.assertEqual(imported["headers"], ["V1", "I1"])
                self.assertEqual(len(imported["samples"]), 3)
                # Sample interval estimation must calculate 0.5s accurately
                interval = RecordingTab._estimate_sample_interval(imported["samples"])
                self.assertEqual(interval, 0.5)

    def test_backward_compatibility_old_imported_file(self):
        """Simulate importing a legacy file that had YYYY-MM-DD timestamps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "legacy.csv"
            import csv, json
            with csv_path.open("w", newline="", encoding="utf-8-sig") as h:
                w = csv.writer(h)
                w.writerow(["PowerAnalyzerRecording/1"])
                w.writerow(["metadata", json.dumps({
                    "format": "PowerAnalyzerRecording/1",
                    "name": "Legacy",
                    "started_at": "2026-10-27T08:00:00",
                    "duration_seconds": 5,
                    "sample_interval_seconds": 1.0,
                    "status": "Finalizado",
                    "stop_reason": "",
                    "headers": ["V1"],
                })])
                w.writerow([])
                w.writerow(["Estampa de tiempo", "V1"])
                w.writerow(["2026-10-27 08:00:00.000", "219.8"])
                w.writerow(["2026-10-27 08:00:01.000", "219.9"])

            imported = RecordingTab._read_recording_file(csv_path, "csv")
            self.assertEqual(len(imported["samples"]), 2)
            interval = RecordingTab._estimate_sample_interval(imported["samples"])
            self.assertEqual(interval, 1.0)

    def test_pdf_table_header_style(self):
        started = datetime(2026, 10, 27, 10, 0, 0)
        samples = [
            ["2026-10-27 10:00:00.000", "220.0"],
            ["2026-10-27 10:00:01.000", "220.2"],
        ]
        recording = Recording(
            record_id=1,
            name="PDF Header Style Test",
            started_at=started,
            duration_seconds=10,
            sample_interval_seconds=1.0,
            status="Finalizado",
            headers=["V1"],
            samples=samples,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "test_header.pdf"
            RecordingTab._write_recording_file(recording, pdf_path, "pdf")

            reader = PdfReader(str(pdf_path))
            content = reader.pages[0].get_contents().get_data().decode("latin1", errors="ignore")

            # Check header background #B7B7B7 (in ReportLab RGB: 183/255 = 0.717647)
            self.assertTrue(
                ".717647 .717647 .717647 rg" in content or "0.717647 0.717647 0.717647 rg" in content,
                "Header background #B7B7B7 not found in PDF stream!"
            )

            # Check that Helvetica-Bold is in font resources
            fonts = reader.pages[0]["/Resources"]["/Font"]
            base_fonts = [fonts[k].get_object()["/BaseFont"] for k in fonts]
            self.assertIn("/Helvetica-Bold", base_fonts)
            self.assertIn("/Helvetica", base_fonts)

            # Check in content stream that /F2 (Helvetica-Bold) is used for header and /F1 (Helvetica) for data
            # Header text is rendered with bold font
            self.assertIn("Estampa de tiempo", reader.pages[0].extract_text())
