import socket
import struct
import threading
import time
import unittest
from datetime import datetime

from PySide6.QtCore import QCoreApplication, Qt

from app.device_manager.device import Device
from app.tes3600.network.protocol import parse_message, MESSAGE_SIZE, TIMESTAMP_SIZE, TES3600_FRAME_SIZE
from app.tes3600.network.tcp_client import TCPClient, HEADER_SIZE
from app.tes3600.services.measurement_service import TCPMeasurementService


def make_valid_raw_frame() -> bytes:
    """Crea una trama binaria válida de 61 bytes para el TES3600."""
    frame = bytearray(TES3600_FRAME_SIZE)
    frame[0] = 0x02  # STX
    frame[-1] = 0x03  # ETX
    # Voltage V1 = 220.0 V (2200 = 0x0898)
    frame[1] = 0x08
    frame[2] = 0x98
    # FP1, FP2, FP3 <= 1.0 (0 en bytes 9-10, 23-24, 37-38)
    return bytes(frame)


def make_tcp_packet(frame: bytes, ms_since_midnight: int = 3600000, length_override: int | None = None) -> bytes:
    """Construye un paquete TCP completo tal como lo genera el servidor TES3600."""
    timestamp_bytes = struct.pack("!I", ms_since_midnight)
    payload = timestamp_bytes + frame
    length = length_override if length_override is not None else len(payload)
    header = struct.pack("!I", length)
    return header + payload


class MockTCPServer:
    """Servidor TCP de prueba para controlar el envío de bytes al cliente."""

    def __init__(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("127.0.0.1", 0))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(1)
        self.client_socket = None
        self.accept_thread = threading.Thread(target=self._accept, daemon=True)
        self.accept_thread.start()

    def _accept(self):
        try:
            self.client_socket, _ = self.server_socket.accept()
        except OSError:
            pass

    def wait_client(self, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.client_socket is not None:
                return True
            time.sleep(0.01)
        return False

    def send(self, data: bytes):
        if self.client_socket:
            self.client_socket.sendall(data)

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


class TestTCPCommunicationAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.mock_server = MockTCPServer()
        self.device = Device(
            id="test-device",
            name="Test TES3600",
            model="TES3600",
            connection_type="tcp",
            host="127.0.0.1",
            port=self.mock_server.port,
        )

    def tearDown(self):
        self.mock_server.close()

    # -------------------------------------------------------------------------
    # Prueba 1: Recepción normal de mediciones de 65 bytes de contenido
    # -------------------------------------------------------------------------
    def test_01_normal_reception_65_bytes(self):
        raw_frame = make_valid_raw_frame()
        packet = make_tcp_packet(raw_frame)
        self.assertEqual(len(packet), 69)  # 4 header + 65 payload

        client = TCPClient(self.device)
        self.assertTrue(self.mock_server.wait_client())

        self.mock_server.send(packet)
        payload = client.receive_message(timeout=1.0)
        client.close()

        self.assertIsNotNone(payload)
        self.assertEqual(len(payload), 65)

        msg = parse_message(payload)
        self.assertEqual(len(msg.frame), 61)
        self.assertEqual(msg.frame[0], 0x02)
        self.assertEqual(msg.frame[-1], 0x03)

    # -------------------------------------------------------------------------
    # Prueba 2: Recepción de una trama con longitud incorrecta
    # -------------------------------------------------------------------------
    def test_02_invalid_length_does_not_break_connection(self):
        bad_payload = b"\x00" * 30  # Anunciar 30 bytes en lugar de 65
        packet = struct.pack("!I", len(bad_payload)) + bad_payload

        client = TCPClient(self.device)
        self.assertTrue(self.mock_server.wait_client())

        # Enviar trama con longitud incorrecta
        self.mock_server.send(packet)
        payload = client.receive_message(timeout=1.0)

        # Se recibe el bloque anunciado pero la validación detecta la anomalía
        self.assertEqual(len(payload), 30)
        with self.assertRaises(ValueError) as ctx:
            parse_message(payload)
        self.assertIn("Longitud incorrecta", str(ctx.exception))

        # La conexión sigue viva y sincronizada: enviamos inmediatamente una válida
        valid_packet = make_tcp_packet(make_valid_raw_frame())
        self.mock_server.send(valid_packet)
        next_payload = client.receive_message(timeout=1.0)
        client.close()

        self.assertIsNotNone(next_payload)
        self.assertEqual(len(next_payload), 65)
        msg = parse_message(next_payload)
        self.assertEqual(msg.frame[0], 0x02)

    # -------------------------------------------------------------------------
    # Prueba 3: Recepción de una trama incompleta (fragmentación TCP)
    # -------------------------------------------------------------------------
    def test_03_fragmented_frame_reception(self):
        packet = make_tcp_packet(make_valid_raw_frame())

        client = TCPClient(self.device)
        self.assertTrue(self.mock_server.wait_client())

        # Enviar la primera mitad (30 bytes de los 69 totales)
        self.mock_server.send(packet[:30])

        # Timeout breve: no se ha completado la trama, retorna None sin perder datos
        partial = client.receive_message(timeout=0.1)
        self.assertIsNone(partial)

        # Enviar los 39 bytes restantes
        self.mock_server.send(packet[30:])
        complete = client.receive_message(timeout=1.0)
        client.close()

        self.assertIsNotNone(complete)
        self.assertEqual(len(complete), 65)
        msg = parse_message(complete)
        self.assertEqual(msg.frame[0], 0x02)

    # -------------------------------------------------------------------------
    # Prueba 4: Recepción de varios mensajes concatenados
    # -------------------------------------------------------------------------
    def test_04_concatenated_messages_in_single_read(self):
        raw1 = make_valid_raw_frame()
        raw2 = make_valid_raw_frame()
        packet1 = make_tcp_packet(raw1, ms_since_midnight=1000)
        packet2 = make_tcp_packet(raw2, ms_since_midnight=2000)

        client = TCPClient(self.device)
        self.assertTrue(self.mock_server.wait_client())

        # Enviar ambos paquetes juntos en un solo sendall
        self.mock_server.send(packet1 + packet2)

        res1 = client.receive_message(timeout=1.0)
        res2 = client.receive_message(timeout=1.0)
        client.close()

        self.assertIsNotNone(res1)
        self.assertIsNotNone(res2)
        self.assertEqual(len(res1), 65)
        self.assertEqual(len(res2), 65)

        msg1 = parse_message(res1)
        msg2 = parse_message(res2)
        self.assertEqual(msg1.millisecond, 0)
        self.assertEqual(msg1.second, 1)
        self.assertEqual(msg2.second, 2)

    # -------------------------------------------------------------------------
    # Prueba 5: Trama inválida seguida de una válida en TCPMeasurementService
    # -------------------------------------------------------------------------
    def test_05_invalid_frame_followed_by_valid_frame_in_service(self):
        service = TCPMeasurementService(self.device, signal_timeout=1.5, read_timeout=0.05)

        received_measurements = []
        statuses = []
        service.measurements_received.connect(
            lambda m: received_measurements.append(m),
            Qt.ConnectionType.DirectConnection,
        )
        service.status_changed.connect(
            lambda s: statuses.append(s),
            Qt.ConnectionType.DirectConnection,
        )

        service.start()
        self.assertTrue(self.mock_server.wait_client())

        # Enviar trama con delimitador erróneo (trama inválida de 65 bytes)
        corrupt_frame = bytearray(61)
        corrupt_frame[0] = 0xFF  # Inválido, no es 0x02
        corrupt_frame[-1] = 0x03
        bad_packet = make_tcp_packet(bytes(corrupt_frame))
        self.mock_server.send(bad_packet)

        # Dar tiempo breve para procesar descarte
        time.sleep(0.1)
        self.assertEqual(len(received_measurements), 0)
        self.assertTrue(service.isRunning())

        # Enviar trama válida
        valid_packet = make_tcp_packet(make_valid_raw_frame())
        self.mock_server.send(valid_packet)

        time.sleep(0.15)
        service.stop()
        service.wait(1000)

        self.assertGreaterEqual(len(received_measurements), 1)
        self.assertIn("Recibiendo", statuses)

    # -------------------------------------------------------------------------
    # Prueba 6: Interrupción de mediciones sin desconexión TCP -> "Sin señal"
    # -------------------------------------------------------------------------
    def test_06_measurements_interrupted_transitions_to_sin_senal(self):
        service = TCPMeasurementService(self.device, signal_timeout=0.3, read_timeout=0.05)

        statuses = []
        service.status_changed.connect(
            lambda s: statuses.append(s),
            Qt.ConnectionType.DirectConnection,
        )

        service.start()
        self.assertTrue(self.mock_server.wait_client())

        # Enviar medición válida inicial
        self.mock_server.send(make_tcp_packet(make_valid_raw_frame()))
        time.sleep(0.1)
        self.assertEqual(service.current_status, "Recibiendo")
        self.assertIn("Recibiendo", statuses)

        # Dejar de enviar datos pero mantener el socket TCP abierto
        # El timeout configurado es 0.3 s, esperamos 0.5 s
        time.sleep(0.5)

        self.assertEqual(service.current_status, "Sin señal")
        self.assertEqual(statuses[-1], "Sin señal")
        # El socket y el servicio siguen activos
        self.assertTrue(service.isRunning())

        service.stop()
        service.wait(1000)

    # -------------------------------------------------------------------------
    # Prueba 7: Reanudación de mediciones después de "Sin señal"
    # -------------------------------------------------------------------------
    def test_07_resume_measurements_after_sin_senal(self):
        service = TCPMeasurementService(self.device, signal_timeout=0.3, read_timeout=0.05)

        statuses = []
        service.status_changed.connect(
            lambda s: statuses.append(s),
            Qt.ConnectionType.DirectConnection,
        )

        service.start()
        self.assertTrue(self.mock_server.wait_client())

        # 1. Enviar primera medición
        self.mock_server.send(make_tcp_packet(make_valid_raw_frame()))
        time.sleep(0.1)
        self.assertEqual(service.current_status, "Recibiendo")

        # 2. Dejar pasar tiempo sin datos -> entra en "Sin señal"
        time.sleep(0.45)
        self.assertEqual(service.current_status, "Sin señal")

        # 3. Reanudar envío de mediciones válidas
        self.mock_server.send(make_tcp_packet(make_valid_raw_frame()))
        time.sleep(0.15)

        self.assertEqual(service.current_status, "Recibiendo")
        self.assertEqual(statuses[-1], "Recibiendo")

        service.stop()
        service.wait(1000)

    # -------------------------------------------------------------------------
    # Prueba 8: Desconexión real del cliente TCP
    # -------------------------------------------------------------------------
    def test_08_real_server_disconnection(self):
        service = TCPMeasurementService(self.device, signal_timeout=1.5, read_timeout=0.05)

        errors = []
        statuses = []
        finished = threading.Event()

        service.error_occurred.connect(
            lambda e: errors.append(e),
            Qt.ConnectionType.DirectConnection,
        )
        service.status_changed.connect(
            lambda s: statuses.append(s),
            Qt.ConnectionType.DirectConnection,
        )
        service.finished.connect(
            lambda: finished.set(),
            Qt.ConnectionType.DirectConnection,
        )

        service.start()
        self.assertTrue(self.mock_server.wait_client())

        # Cerrar el socket desde el servidor abruptamente
        self.mock_server.close_client()

        # El servicio debe detectar el fin de conexión, notificar y terminar
        self.assertTrue(finished.wait(timeout=2.0))
        self.assertFalse(service.isRunning())
        self.assertGreaterEqual(len(errors), 1)
        self.assertIn("El servidor TCP cerró la conexión.", errors[0])


if __name__ == "__main__":
    unittest.main()
