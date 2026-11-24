import struct
import unittest

from app.tes3600.decoder import TES3600Decoder


def build_tes3600_frame(
    q1: float = 10.0,
    theta1: float = 30.0,
    q2: float = 20.0,
    theta2: float = 45.0,
    q3: float = 30.0,
    theta3: float = 60.0,
    qt: float = 60.0,
    st: float = 100.0,
    pt: float = 80.0,
    byte_59_signs: int = 0,
    frame_length: int = 61,
) -> bytes:
    """Construye una trama sintética de TES3600 para pruebas de decodificación y signos."""
    frame = bytearray(frame_length)
    if frame_length > 0:
        frame[0] = TES3600Decoder.FRAME_START
    if frame_length > 1:
        frame[-1] = TES3600Decoder.FRAME_END

    def write_u16(offset: int, val: int):
        if offset + 2 <= frame_length:
            frame[offset : offset + 2] = struct.pack("!H", val)

    # V1=220.0, I1=10.0, S1=22.0, P1=20.0, FP1=0.8, Theta1=30.0, Q1=10.0
    write_u16(1, 2200)
    write_u16(3, 100)
    write_u16(5, 220)
    write_u16(7, 200)
    write_u16(9, 800)  # FP1 = 0.8
    write_u16(11, int(round(theta1 * 10)))
    write_u16(13, int(round(q1 * 10)))

    # V2, I2, S2, P2, FP2, Theta2, Q2
    write_u16(15, 2200)
    write_u16(17, 100)
    write_u16(19, 220)
    write_u16(21, 200)
    write_u16(23, 800)  # FP2 = 0.8
    write_u16(25, int(round(theta2 * 10)))
    write_u16(27, int(round(q2 * 10)))

    # V3, I3, S3, P3, FP3, Theta3, Q3
    write_u16(29, 2200)
    write_u16(31, 100)
    write_u16(33, 220)
    write_u16(35, 200)
    write_u16(37, 800)  # FP3 = 0.8
    write_u16(39, int(round(theta3 * 10)))
    write_u16(41, int(round(q3 * 10)))

    # ST, PT, QT, F, I4
    write_u16(43, int(round(st * 10)))
    write_u16(45, int(round(pt * 10)))
    write_u16(51, int(round(qt * 10)))
    write_u16(53, 500)  # 50.0 Hz
    write_u16(55, 10)   # I4 = 1.0 A

    if frame_length > 58:
        frame[58] = byte_59_signs

    return bytes(frame)


class TestTES3600DecoderSigns(unittest.TestCase):
    def setUp(self):
        self.decoder = TES3600Decoder()

    def test_all_phases_positive(self):
        """Escenario: Cada fase con signo positivo (patrones sin '10')."""
        # signs = 0b000000
        frame = build_tes3600_frame(
            q1=10.0, theta1=30.0,
            q2=20.0, theta2=45.0,
            q3=30.0, theta3=60.0,
            qt=60.0,
            byte_59_signs=0b000000,
        )
        res = self.decoder.decode(frame)
        self.assertIsNotNone(res)
        self.assertEqual(res["kVAR1"], 10.0)
        self.assertEqual(res["Theta1"], 30.0)
        self.assertEqual(res["kVAR2"], 20.0)
        self.assertEqual(res["Theta2"], 45.0)
        self.assertEqual(res["kVAR3"], 30.0)
        self.assertEqual(res["Theta3"], 60.0)
        self.assertEqual(res["TkVAR"], 60.0)
        self.assertGreater(res["TTheta1"], 0)

    def test_non_inverting_bit_patterns(self):
        """Escenario: Patrones de bits 00, 01 y 11 no deben invertir signos."""
        # Fase 1: 01, Fase 2: 11, Fase 3: 01 -> signs = 0b011101
        frame = build_tes3600_frame(
            q1=15.0, theta1=25.0,
            q2=25.0, theta2=35.0,
            q3=35.0, theta3=45.0,
            qt=75.0,
            byte_59_signs=0b011101,
        )
        res = self.decoder.decode(frame)
        self.assertIsNotNone(res)
        self.assertEqual(res["kVAR1"], 15.0)
        self.assertEqual(res["Theta1"], 25.0)
        self.assertEqual(res["kVAR2"], 25.0)
        self.assertEqual(res["Theta2"], 35.0)
        self.assertEqual(res["kVAR3"], 35.0)
        self.assertEqual(res["Theta3"], 45.0)
        self.assertEqual(res["TkVAR"], 75.0)

    def test_independent_negative_phase_1(self):
        """Escenario: Fase 1 con signo negativo de manera independiente."""
        # signs = 0b000010 (bits 0-1 = 10)
        frame = build_tes3600_frame(
            q1=10.0, theta1=30.0,
            q2=20.0, theta2=45.0,
            q3=30.0, theta3=60.0,
            qt=60.0,
            byte_59_signs=0b000010,
        )
        res = self.decoder.decode(frame)
        self.assertIsNotNone(res)
        self.assertEqual(res["kVAR1"], -10.0)
        self.assertEqual(res["Theta1"], -30.0)
        self.assertEqual(res["kVAR2"], 20.0)
        self.assertEqual(res["Theta2"], 45.0)
        self.assertEqual(res["kVAR3"], 30.0)
        self.assertEqual(res["Theta3"], 60.0)

    def test_independent_negative_phase_2(self):
        """Escenario: Fase 2 con signo negativo de manera independiente."""
        # signs = 0b001000 (bits 2-3 = 10)
        frame = build_tes3600_frame(
            q1=10.0, theta1=30.0,
            q2=20.0, theta2=45.0,
            q3=30.0, theta3=60.0,
            qt=60.0,
            byte_59_signs=0b001000,
        )
        res = self.decoder.decode(frame)
        self.assertIsNotNone(res)
        self.assertEqual(res["kVAR1"], 10.0)
        self.assertEqual(res["Theta1"], 30.0)
        self.assertEqual(res["kVAR2"], -20.0)
        self.assertEqual(res["Theta2"], -45.0)
        self.assertEqual(res["kVAR3"], 30.0)
        self.assertEqual(res["Theta3"], 60.0)

    def test_independent_negative_phase_3(self):
        """Escenario: Fase 3 con signo negativo de manera independiente."""
        # signs = 0b100000 (bits 4-5 = 10)
        frame = build_tes3600_frame(
            q1=10.0, theta1=30.0,
            q2=20.0, theta2=45.0,
            q3=30.0, theta3=60.0,
            qt=60.0,
            byte_59_signs=0b100000,
        )
        res = self.decoder.decode(frame)
        self.assertIsNotNone(res)
        self.assertEqual(res["kVAR1"], 10.0)
        self.assertEqual(res["Theta1"], 30.0)
        self.assertEqual(res["kVAR2"], 20.0)
        self.assertEqual(res["Theta2"], 45.0)
        self.assertEqual(res["kVAR3"], -30.0)
        self.assertEqual(res["Theta3"], -60.0)

    def test_two_and_three_phases_negative(self):
        """Escenario: Dos o tres fases con signo negativo."""
        # Fases 1 y 2 negativas: signs = 0b001010
        # Q1=-10, Q2=-10, Q3=30 -> Q1+Q2+Q3 = 10 > 0 (suma positiva)
        frame = build_tes3600_frame(
            q1=10.0, theta1=30.0,
            q2=10.0, theta2=45.0,
            q3=30.0, theta3=60.0,
            qt=50.0,
            byte_59_signs=0b001010,
        )
        res = self.decoder.decode(frame)
        self.assertEqual(res["kVAR1"], -10.0)
        self.assertEqual(res["Theta1"], -30.0)
        self.assertEqual(res["kVAR2"], -10.0)
        self.assertEqual(res["Theta2"], -45.0)
        self.assertEqual(res["kVAR3"], 30.0)
        self.assertEqual(res["Theta3"], 60.0)
        # Suma es 10 > 0, QT no debe invertirse
        self.assertEqual(res["TkVAR"], 50.0)
        self.assertGreater(res["TTheta1"], 0)

        # Fases 1, 2 y 3 negativas: signs = 0b101010
        frame_all_neg = build_tes3600_frame(
            q1=10.0, theta1=30.0,
            q2=20.0, theta2=45.0,
            q3=30.0, theta3=60.0,
            qt=60.0,
            byte_59_signs=0b101010,
        )
        res_all_neg = self.decoder.decode(frame_all_neg)
        self.assertEqual(res_all_neg["kVAR1"], -10.0)
        self.assertEqual(res_all_neg["Theta1"], -30.0)
        self.assertEqual(res_all_neg["kVAR2"], -20.0)
        self.assertEqual(res_all_neg["Theta2"], -45.0)
        self.assertEqual(res_all_neg["kVAR3"], -30.0)
        self.assertEqual(res_all_neg["Theta3"], -60.0)
        # Suma = -60 < 0 -> QT y ThT se invierten
        self.assertEqual(res_all_neg["TkVAR"], -60.0)
        self.assertLess(res_all_neg["TTheta1"], 0)

    def test_sum_q1_q2_q3_positive(self):
        """Escenario: Suma de Q1 + Q2 + Q3 positiva -> QT y ThT NO se invierten."""
        # Q1 = -10, Q2 = 25, Q3 = 10 -> Suma = 25 > 0
        frame = build_tes3600_frame(
            q1=10.0, theta1=30.0,
            q2=25.0, theta2=45.0,
            q3=10.0, theta3=60.0,
            qt=45.0,
            byte_59_signs=0b000010,  # solo Fase 1 negativa
        )
        res = self.decoder.decode(frame)
        self.assertEqual(res["kVAR1"], -10.0)
        self.assertEqual(res["kVAR2"], 25.0)
        self.assertEqual(res["kVAR3"], 10.0)
        self.assertEqual(res["TkVAR"], 45.0)
        self.assertGreater(res["TTheta1"], 0)

    def test_sum_q1_q2_q3_negative(self):
        """Escenario: Suma de Q1 + Q2 + Q3 negativa -> QT y ThT SE invierten."""
        # Q1 = -40, Q2 = 10, Q3 = 10 -> Suma = -20 < 0
        frame = build_tes3600_frame(
            q1=40.0, theta1=30.0,
            q2=10.0, theta2=45.0,
            q3=10.0, theta3=60.0,
            qt=60.0,
            byte_59_signs=0b000010,  # solo Fase 1 negativa
        )
        res = self.decoder.decode(frame)
        self.assertEqual(res["kVAR1"], -40.0)
        self.assertEqual(res["kVAR2"], 10.0)
        self.assertEqual(res["kVAR3"], 10.0)
        self.assertEqual(res["TkVAR"], -60.0)
        self.assertLess(res["TTheta1"], 0)

    def test_sum_q1_q2_q3_zero(self):
        """Escenario: Suma de Q1 + Q2 + Q3 igual a cero -> QT y ThT NO se invierten."""
        # Q1 = -20, Q2 = 10, Q3 = 10 -> Suma = 0
        frame = build_tes3600_frame(
            q1=20.0, theta1=30.0,
            q2=10.0, theta2=45.0,
            q3=10.0, theta3=60.0,
            qt=40.0,
            byte_59_signs=0b000010,  # Fase 1 negativa (-20), Fase 2 y 3 positivas (+10, +10)
        )
        res = self.decoder.decode(frame)
        self.assertEqual(res["kVAR1"], -20.0)
        self.assertEqual(res["kVAR2"], 10.0)
        self.assertEqual(res["kVAR3"], 10.0)
        # Suma es 0, no es < 0, por ende QT y TTheta1 no deben invertirse
        self.assertEqual(res["TkVAR"], 40.0)
        self.assertGreater(res["TTheta1"], 0)

    def test_frame_length_check(self):
        """Escenario: Validación de longitud de trama."""
        # Trama menor a FRAME_SIZE (61 bytes)
        short_frame = b"\x02" + b"\x00" * 50 + b"\x03"
        self.assertIsNone(self.decoder.decode(short_frame))

        # Trama vacía
        self.assertIsNone(self.decoder.decode(b""))

        # Trama de 60 bytes (le falta el byte final)
        frame_60 = b"\x02" + b"\x00" * 59
        self.assertIsNone(self.decoder.decode(frame_60))


if __name__ == "__main__":
    unittest.main()
