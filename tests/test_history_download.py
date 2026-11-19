"""Pruebas unitarias y de integración para la descarga de mediciones históricas."""

import os
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QDate, QTime, Qt
from PySide6.QtWidgets import QApplication

from app.device_manager.device import Device
from app.tes3600.decoder import TES3600Decoder
from app.tes3600.network.history_client import (
    HistoryTCPClient,
    HEADER_SIZE,
    RECORD_PAYLOAD_SIZE,
    TOTAL_RECORD_SIZE,
)
from app.tes3600.network.protocol import (
    parse_message,
    MESSAGE_SIZE_LEGACY,
    MESSAGE_SIZE_UNIFIED,
    ReceivedMessage,
)
from app.tes3600.services.history_service import (
    HistoryDownloadWorker,
    estimate_sample_interval,
)
from app.ui.widgets.tes3600.recording_tab import RecordingTab, Recording
from app.ui.widgets.tes3600.history_download_widget import HistoryDownloadWidget


def make_valid_tes3600_frame() -> bytes:
    """Genera una trama TES3600 válida de 61 bytes."""
    frame = bytearray(61)
    frame[0] = 0x02  # STX
    frame[-1] = 0x03  # ETX
    # V1 = 220.0 V (2200 = 0x0898)
    frame[1] = 0x08
    frame[2] = 0x98
    # I1 = 10.0 A (100 = 0x0064)
    frame[3] = 0x00
    frame[4] = 0x64
    # S1 = 2.2 kVA (22 = 0x0016)
    frame[5] = 0x00
    frame[6] = 0x16
    # P1 = 2.2 kW
    frame[7] = 0x00
    frame[8] = 0x16
    return bytes(frame)


def make_unified_history_packet(timestamp_ms: int, frame: bytes) -> bytes:
    """Genera un paquete unificado del historial: 4B header (69) + 8B timestamp_ms + 61B frame = 73B."""
    header = struct.pack("!I", RECORD_PAYLOAD_SIZE)
    timestamp = struct.pack("!Q", timestamp_ms)
    return header + timestamp + frame


class MockHistoryServer:
    """Servidor TCP simulado para pruebas de descarga histórica."""

    def __init__(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("127.0.0.1", 0))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(1)

        self.client_socket: socket.socket | None = None
        self.received_request = bytearray()
        self.accept_thread = threading.Thread(target=self._accept, daemon=True)
        self.accept_thread.start()

    def _accept(self):
        try:
            self.client_socket, _ = self.server_socket.accept()
        except OSError:
            pass

    def wait_client(self, timeout=2.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.client_socket is not None:
                return True
            time.sleep(0.01)
        return False

    def read_request(self, size: int, timeout=2.0) -> bytes:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.client_socket:
                try:
                    self.client_socket.settimeout(0.1)
                    chunk = self.client_socket.recv(size - len(self.received_request))
                    if chunk:
                        self.received_request.extend(chunk)
                        if len(self.received_request) >= size:
                            return bytes(self.received_request[:size])
                except (socket.timeout, OSError):
                    pass
            time.sleep(0.01)
        return bytes(self.received_request)

    def send(self, data: bytes):
        if self.client_socket:
            self.client_socket.sendall(data)

    def send_end_of_transmission(self):
        """Envía los 4 bytes con valor cero que señalan el final de la descarga."""
        self.send(struct.pack("!I", 0))

    def close_client(self):
        if self.client_socket:
            try:
                self.client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.client_socket.close()
            self.client_socket = None

    def close(self):
        self.close_client()
        try:
            self.server_socket.close()
        except OSError:
            pass
        self.accept_thread.join(timeout=1.0)


class TestHistoryDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.mock_server = MockHistoryServer()

    def tearDown(self):
        self.mock_server.close()

    # -------------------------------------------------------------------------
    # 1. Decodificación correcta de un mensaje de 73 bytes
    # -------------------------------------------------------------------------
    def test_01_decode_73_byte_unified_message(self):
        now_ms = int(datetime(2026, 11, 16, 14, 30, 0, 500000).timestamp() * 1000)
        raw_frame = make_valid_tes3600_frame()
        packet = make_unified_history_packet(now_ms, raw_frame)
        self.assertEqual(len(packet), 73)

        payload_len = struct.unpack("!I", packet[:4])[0]
        self.assertEqual(payload_len, 69)

        payload = packet[4:]
        msg = parse_message(payload)
        self.assertIsInstance(msg, ReceivedMessage)
        self.assertEqual(msg.hour, 14)
        self.assertEqual(msg.minute, 30)
        self.assertEqual(msg.second, 0)
        self.assertEqual(msg.millisecond, 500)
        self.assertEqual(msg.unix_timestamp_ms, now_ms)
        self.assertEqual(len(msg.frame), 61)

        decoder = TES3600Decoder()
        measurements = decoder.decode(msg.frame)
        self.assertIsNotNone(measurements)
        self.assertEqual(measurements["V1"], 220.0)
        self.assertEqual(measurements["I1"], 10.0)

    # -------------------------------------------------------------------------
    # 2. Lectura TCP de mensajes fragmentados
    # -------------------------------------------------------------------------
    def test_02_fragmented_tcp_reception(self):
        client = HistoryTCPClient("127.0.0.1", self.mock_server.port)
        client.connect()
        self.assertTrue(self.mock_server.wait_client())

        now_ms = 1700000000000
        packet = make_unified_history_packet(now_ms, make_valid_tes3600_frame())
        terminator = struct.pack("!I", 0)
        stream = packet + terminator

        # Enviar stream fragmentado en trozos pequeños de 7 bytes
        def send_fragments():
            chunk_size = 7
            for i in range(0, len(stream), chunk_size):
                self.mock_server.send(stream[i:i + chunk_size])
                time.sleep(0.005)

        t = threading.Thread(target=send_fragments)
        t.start()

        records = list(client.iter_records())
        t.join()
        client.close()

        self.assertEqual(len(records), 1)
        ts, frame = records[0]
        self.assertEqual(ts, now_ms)
        self.assertEqual(len(frame), 61)

    # -------------------------------------------------------------------------
    # 3. Lectura de varios registros consecutivos
    # -------------------------------------------------------------------------
    def test_03_multiple_consecutive_records(self):
        client = HistoryTCPClient("127.0.0.1", self.mock_server.port)
        client.connect()
        self.assertTrue(self.mock_server.wait_client())

        base_ms = 1700000000000
        stream = bytearray()
        count = 10
        for i in range(count):
            stream.extend(make_unified_history_packet(base_ms + i * 500, make_valid_tes3600_frame()))
        stream.extend(struct.pack("!I", 0))

        self.mock_server.send(bytes(stream))

        records = list(client.iter_records())
        client.close()

        self.assertEqual(len(records), count)
        for i, (ts, frame) in enumerate(records):
            self.assertEqual(ts, base_ms + i * 500)
            self.assertEqual(len(frame), 61)

    # -------------------------------------------------------------------------
    # 4. Detección del final de descarga mediante longitud cero
    # -------------------------------------------------------------------------
    def test_04_detection_end_of_transmission_zero_length(self):
        client = HistoryTCPClient("127.0.0.1", self.mock_server.port)
        client.connect()
        self.assertTrue(self.mock_server.wait_client())

        now_ms = 1700000000000
        packet = make_unified_history_packet(now_ms, make_valid_tes3600_frame())
        terminator = struct.pack("!I", 0)
        self.mock_server.send(packet + terminator)

        gen = client.iter_records()
        record = next(gen)
        self.assertIsNotNone(record)

        # La siguiente llamada debe terminar normalmente sin excepciones
        with self.assertRaises(StopIteration):
            next(gen)

        client.close()

    # -------------------------------------------------------------------------
    # 5. Envío correcto de solicitudes predefinidas (0x01 a 0x09)
    # -------------------------------------------------------------------------
    def test_05_send_predefined_requests(self):
        for code in (0x01, 0x05, 0x09):
            server = MockHistoryServer()
            client = HistoryTCPClient("127.0.0.1", server.port)
            client.connect()
            self.assertTrue(server.wait_client())

            client.send_predefined_request(code)
            req = server.read_request(1)
            self.assertEqual(len(req), 1)
            self.assertEqual(req[0], code)

            client.close()
            server.close()

    # -------------------------------------------------------------------------
    # 6. Envío correcto de solicitudes personalizadas (0x0F + timestamps)
    # -------------------------------------------------------------------------
    def test_06_send_custom_request(self):
        client = HistoryTCPClient("127.0.0.1", self.mock_server.port)
        client.connect()
        self.assertTrue(self.mock_server.wait_client())

        start_ms = 1700000000000
        end_ms = 1700003600000
        client.send_custom_request(start_ms, end_ms)

        req = self.mock_server.read_request(17)
        self.assertEqual(len(req), 17)
        self.assertEqual(req[0], 0x0F)
        unpacked_start, unpacked_end = struct.unpack("!QQ", req[1:])
        self.assertEqual(unpacked_start, start_ms)
        self.assertEqual(unpacked_end, end_ms)

        client.close()

    # -------------------------------------------------------------------------
    # 7. Manejo de desconexiones durante una descarga
    # -------------------------------------------------------------------------
    def test_07_disconnection_during_download(self):
        client = HistoryTCPClient("127.0.0.1", self.mock_server.port, timeout=0.5)
        client.connect()
        self.assertTrue(self.mock_server.wait_client())

        now_ms = 1700000000000
        packet = make_unified_history_packet(now_ms, make_valid_tes3600_frame())
        # Enviar un registro y luego cortar la conexión abruptamente sin terminador
        self.mock_server.send(packet)
        time.sleep(0.05)
        self.mock_server.close_client()

        with self.assertRaises(ConnectionError):
            list(client.iter_records())

        client.close()

    # -------------------------------------------------------------------------
    # 8. Manejo de respuestas vacías (terminador inmediato)
    # -------------------------------------------------------------------------
    def test_08_empty_response_immediate_terminator(self):
        client = HistoryTCPClient("127.0.0.1", self.mock_server.port)
        client.connect()
        self.assertTrue(self.mock_server.wait_client())

        self.mock_server.send_end_of_transmission()
        records = list(client.iter_records())
        client.close()

        self.assertEqual(len(records), 0)

    # -------------------------------------------------------------------------
    # 9. Funcionamiento asíncrono con HistoryDownloadWorker
    # -------------------------------------------------------------------------
    def test_09_worker_async_execution(self):
        worker = HistoryDownloadWorker(
            host="127.0.0.1",
            port=self.mock_server.port,
            request_mode="predefined",
            name="Descarga Async",
            destination_mode="internal",
            period_code=0x01,
        )

        completed_data = {}
        finished_event = threading.Event()

        def on_finished(res):
            completed_data.update(res)
            finished_event.set()

        worker.finished_successfully.connect(
            on_finished,
            Qt.ConnectionType.DirectConnection,
        )
        worker.start()

        self.assertTrue(self.mock_server.wait_client())
        _ = self.mock_server.read_request(1)

        base_ms = 1700000000000
        stream = bytearray()
        for i in range(5):
            stream.extend(make_unified_history_packet(base_ms + i * 500, make_valid_tes3600_frame()))
        stream.extend(struct.pack("!I", 0))
        self.mock_server.send(bytes(stream))

        finished_event.wait(timeout=3.0)
        worker.wait(1000)

        self.assertTrue(finished_event.is_set())
        self.assertEqual(completed_data.get("count"), 5)
        self.assertEqual(len(completed_data.get("samples", [])), 5)
        self.assertEqual(completed_data.get("name"), "Descarga Async")

    # -------------------------------------------------------------------------
    # 10. Creación correcta de un nuevo registro interno en RecordingTab
    # 11. Asignación y conservación del nombre del registro
    # 12. Actualización de la lista de registros
    # -------------------------------------------------------------------------
    @patch("PySide6.QtWidgets.QMessageBox.information")
    def test_10_11_12_internal_recording_creation_and_table_update(self, mock_info):
        tab = RecordingTab()
        initial_count = len(tab._recordings)

        # Simular resultado de descarga histórica
        samples = [
            ["2026-11-16 10:00:00.000", 220.0, 10.0, 2.2, 2.2, 1.0, 0.0, 0.0],
            ["2026-11-16 10:00:00.500", 220.5, 10.1, 2.2, 2.2, 1.0, 0.0, 0.0],
        ]
        headers = ["V1", "I1", "kVA1", "kW1", "FP1", "kVAR1", "Theta1"]

        result = {
            "name": "Ensayo Transformador 1",
            "started_at": datetime(2026, 11, 16, 10, 0, 0),
            "duration_seconds": 1,
            "sample_interval_seconds": 0.5,
            "headers": headers,
            "samples": samples,
            "destination_mode": "internal",
            "count": len(samples),
        }

        # Ejecutar la integración
        tab._on_history_download_completed(result)

        self.assertEqual(len(tab._recordings), initial_count + 1)
        new_rec = list(tab._recordings.values())[-1]
        self.assertEqual(new_rec.name, "Ensayo Transformador 1")
        self.assertEqual(new_rec.status, "Finalizado")
        self.assertEqual(new_rec.stop_reason, "Descarga desde servidor")
        self.assertEqual(len(new_rec.samples), 2)
        self.assertEqual(tab.table.rowCount(), len(tab._recordings))

        # Verificar que una segunda descarga crea OTRA entidad sin sobrescribir
        result2 = dict(result, name="Ensayo Transformador 2")
        tab._on_history_download_completed(result2)
        self.assertEqual(len(tab._recordings), initial_count + 2)
        self.assertEqual(list(tab._recordings.values())[-1].name, "Ensayo Transformador 2")

    # -------------------------------------------------------------------------
    # 13. Exportación local utilizando los mecanismos existentes (CSV, TXT, XLSX)
    # 14. Ausencia de creación de registros internos cuando se elige archivo local
    # -------------------------------------------------------------------------
    @patch("PySide6.QtWidgets.QMessageBox.information")
    def test_13_14_export_local_file_no_internal_recording_created(self, mock_info):
        tab = RecordingTab()
        initial_count = len(tab._recordings)

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "descarga_prueba.csv"
            samples = [
                ["2026-11-16 12:00:00.000", 220.0, 5.0, 1.1, 1.1],
                ["2026-11-16 12:00:00.500", 221.0, 5.2, 1.1, 1.1],
            ]
            headers = ["V1", "I1", "kVA1", "kW1"]

            result = {
                "name": "descarga_prueba",
                "started_at": datetime(2026, 11, 16, 12, 0, 0),
                "duration_seconds": 1,
                "sample_interval_seconds": 0.5,
                "headers": headers,
                "samples": samples,
                "destination_mode": "local_file",
                "export_path": csv_path,
                "export_extension": "csv",
                "count": len(samples),
            }

            tab._on_history_download_completed(result)

            # Verificar que el archivo existe y no está vacío
            self.assertTrue(csv_path.exists())
            self.assertGreater(csv_path.stat().st_size, 0)

            # Verificar que NO se agregó ningún registro interno a la colección
            self.assertEqual(len(tab._recordings), initial_count)

            # Verificar contenido del archivo exportado leyendo con el parser existente
            imported = tab._read_recording_file(csv_path, "csv")
            self.assertEqual(imported["headers"], headers)
            self.assertEqual(len(imported["samples"]), 2)

    # -------------------------------------------------------------------------
    # 15. Conservación del funcionamiento de la medición en tiempo real (ambos formatos)
    # -------------------------------------------------------------------------
    def test_15_real_time_protocol_dual_compatibility(self):
        raw_frame = make_valid_tes3600_frame()

        # Formato legacy (65 bytes payload = 4B ms desde medianoche + 61B frame)
        legacy_payload = struct.pack("!I", 3600000) + raw_frame
        self.assertEqual(len(legacy_payload), MESSAGE_SIZE_LEGACY)
        msg_legacy = parse_message(legacy_payload)
        self.assertEqual(msg_legacy.hour, 1)
        self.assertEqual(msg_legacy.minute, 0)
        self.assertEqual(len(msg_legacy.frame), 61)

        # Formato unificado definitivo (69 bytes payload = 8B Unix ms + 61B frame)
        unix_ms = 1700000000000
        unified_payload = struct.pack("!Q", unix_ms) + raw_frame
        self.assertEqual(len(unified_payload), MESSAGE_SIZE_UNIFIED)
        msg_unified = parse_message(unified_payload)
        self.assertEqual(msg_unified.unix_timestamp_ms, unix_ms)
        self.assertEqual(len(msg_unified.frame), 61)
        self.assertIsNotNone(msg_unified.timestamp)

    # -------------------------------------------------------------------------
    # 16. Pruebas de interfaz y validaciones de HistoryDownloadWidget
    # -------------------------------------------------------------------------
    @patch("PySide6.QtWidgets.QMessageBox.warning")
    def test_16_history_download_widget_validations(self, mock_warning):
        widget = HistoryDownloadWidget(default_host="192.168.1.100", default_port=9001)

        # 1. Nombre vacío
        widget.name_input.setText("")
        self.assertFalse(widget._validate_inputs())
        mock_warning.assert_called()

        # 2. Modo archivo local sin ruta
        widget.name_input.setText("TestDescarga")
        widget.destination_combo.setCurrentText("Descargar en archivo local")
        widget.path_input.setText("")
        self.assertFalse(widget._validate_inputs())

        # 3. Período personalizado inválido (fin antes de inicio)
        widget.destination_combo.setCurrentText("Guardar en Power Analyzer (registro interno)")
        widget.period_combo.setCurrentIndex(widget.period_combo.findData(0x0F))
        widget.start_date_edit.setDate(QDate(2026, 11, 15))
        widget.end_date_edit.setDate(QDate(2026, 11, 10))
        self.assertFalse(widget._validate_inputs())

        # 4. Período personalizado con fecha final en el futuro
        future = datetime.now() + timedelta(days=2)
        widget.start_date_edit.setDate(QDate(2026, 11, 1))
        widget.end_date_edit.setDate(QDate(future.year, future.month, future.day))
        self.assertFalse(widget._validate_inputs())

        # 5. Período personalizado con más de 30 días de antigüedad
        past = datetime.now() - timedelta(days=45)
        widget.start_date_edit.setDate(QDate(past.year, past.month, past.day))
        widget.end_date_edit.setDate(QDate.currentDate())
        self.assertFalse(widget._validate_inputs())

    # -------------------------------------------------------------------------
    # 17. Navegación por pestañas internas en RecordingTab
    # -------------------------------------------------------------------------
    def test_17_internal_tab_navigation_in_recording_tab(self):
        tab = RecordingTab()

        # Al inicio solo existe la pestaña 'Registros' y la barra de pestañas está oculta
        self.assertEqual(tab.inner_tabs.count(), 1)
        self.assertTrue(tab.inner_tabs.tabBar().isHidden())

        # Al presionar 'Descargar desde servidor' se abre la pestaña interna
        tab._open_download_tab()
        self.assertEqual(tab.inner_tabs.count(), 2)
        self.assertFalse(tab.inner_tabs.tabBar().isHidden())
        self.assertEqual(tab.inner_tabs.tabText(1), "Descarga desde servidor")
        self.assertEqual(tab.inner_tabs.currentIndex(), 1)

        # Si se presiona nuevamente, no duplica la pestaña, solo la selecciona
        tab.inner_tabs.setCurrentIndex(0)
        tab._open_download_tab()
        self.assertEqual(tab.inner_tabs.count(), 2)
        self.assertEqual(tab.inner_tabs.currentIndex(), 1)

        # Al cerrar la pestaña de descarga regresa a 'Registros' y oculta la barra
        tab._close_download_tab()
        self.assertEqual(tab.inner_tabs.count(), 1)
        self.assertTrue(tab.inner_tabs.tabBar().isHidden())
        self.assertEqual(tab.inner_tabs.currentIndex(), 0)

    # -------------------------------------------------------------------------
    # 18. Configuración y persistencia de history_port en Device
    # -------------------------------------------------------------------------
    def test_18_device_history_port_configuration(self):
        device = Device(
            name="TES Central",
            model="TES3600",
            connection_type="tcp",
            host="192.168.1.50",
            port=9000,
            history_port=9001,
        )
        d = device.to_dict()
        self.assertEqual(d["history_port"], 9001)

        # Recrear desde diccionario (retrocompatibilidad)
        reconstructed = Device.from_dict(d)
        self.assertEqual(reconstructed.history_port, 9001)

        # Diccionario sin history_port adopta el valor por defecto 9001
        legacy_dict = {
            "name": "TES Legacy",
            "model": "TES3600",
            "connection_type": "tcp",
            "host": "192.168.1.51",
            "port": 5000,
        }
        legacy_device = Device.from_dict(legacy_dict)
        self.assertEqual(legacy_device.history_port, 9001)


if __name__ == "__main__":
    unittest.main()
