import math


class TES3600Decoder:
    """Decodificador parcial del analizador TES3600."""

    FRAME_SIZE = 61
    FRAME_START = 0x02
    FRAME_END = 0x03

    def decode(self, frame: bytes) -> dict | None:
        """Decodifica los campos conocidos de una trama TES3600."""

        if len(frame) != self.FRAME_SIZE:
            return None

        if (
            frame[0] != self.FRAME_START
            or frame[-1] != self.FRAME_END
        ):
            return None

        v1 = self._read_uint16(frame, 1) / 10
        i1 = self._read_uint16(frame, 3) / 10
        s1 = self._read_uint16(frame, 5) / 10
        p1 = self._read_uint16(frame, 7) / 10
        fp1 = self._read_uint16(frame, 9) / 1000
        theta1 = self._read_uint16(frame, 11) / 10
        q1 = self._read_uint16(frame, 13) / 10

        v2 = self._read_uint16(frame, 15) / 10
        i2 = self._read_uint16(frame, 17) / 10
        s2 = self._read_uint16(frame, 19) / 10
        p2 = self._read_uint16(frame, 21) / 10
        fp2 = self._read_uint16(frame, 23) / 1000
        theta2 = self._read_uint16(frame, 25) / 10
        q2 = self._read_uint16(frame, 27) / 10
        
        v3 = self._read_uint16(frame, 29) / 10
        i3 = self._read_uint16(frame, 31) / 10
        s3 = self._read_uint16(frame, 33) / 10
        p3 = self._read_uint16(frame, 35) / 10
        fp3 = self._read_uint16(frame, 37) / 1000
        theta3 = self._read_uint16(frame, 39) / 10
        q3 = self._read_uint16(frame, 41) / 10
        
        st = self._read_uint16(frame,43) / 10
        pt = self._read_uint16(frame,45) / 10
#        fpt = self._read_uint16(frame,47) / 10
#        tht = self._read_uint16(frame,49) / 10
        qt = self._read_uint16(frame,51) / 10
        
        f = self._read_uint16(frame,53) / 10
        i4 = self._read_uint16(frame,55) / 10
                
        # Validación preliminar de los valores conocidos.
        if fp1 > 1.0:
            return None
        if fp2 > 1.0:
            return None
        if fp3 > 1.0:
            return None

        """        # Si P supera S más allá del margen de redondeo,
        # no calculamos una potencia reactiva ficticia.
        if abs(p1) > s1 + 0.2:
            q1 = 0
        else:
            q1 = round(math.sqrt(max(0.0, s1**2 - p1**2)),1)
        if abs(p2) > s2 + 0.2:
            q2 = 0
        else:
            q2 = round(math.sqrt(max(0.0, s2**2 - p2**2)),1)
        if abs(p3) > s3 + 0.2:
            q3 = 0
        else:
            q3 = round(math.sqrt(max(0.0, s3**2 - p3**2)),1)"""
            
#        pt = round(p1 + p2 + p3, 1)
#        qt = round(q1 + q2 + q3, 1)
#        st = round(s1 + s2 + s3, 1)
        if st != 0:
            fpt = round(pt/st, 3)
        else:
            fpt = 0
        if fpt != 0:
            thetat = round(math.degrees(math.acos(fpt)), 1)
        else:
            thetat = 0
        
        if len(frame) < 59:
            return None

        signs = frame[58]

        if (signs & 0b11) == 0b10:
            q1 = -q1
            theta1 = -theta1

        if (signs & 0b1100) == 0b1000:
            q2 = -q2
            theta2 = -theta2

        if (signs & 0b110000) == 0b100000:
            q3 = -q3
            theta3 = -theta3

        if q1 + q2 + q3 < 0:
            qt = -qt
            thetat = -thetat
        
        return {
            "V1": v1,"I1": i1,"kVA1": s1,"kW1": p1,"FP1": fp1,"kVAR1": q1,"Theta1": theta1,
            "V2": v2,"I2": i2,"kVA2": s2,"kW2": p2,"FP2": fp2,"kVAR2": q2,"Theta2": theta2,
            "V3": v3,"I3": i3,"kVA3": s3,"kW3": p3,"FP3": fp3,"kVAR3": q3,"Theta3": theta3,
            "TkVA": st,"TkW": pt,"TFP": fpt,"TkVAR": qt,"TTheta1": thetat, "Hz": f, "I4": i4
        }

    @staticmethod
    def _read_uint16(frame: bytes, offset: int) -> int:
        """Lee un entero sin signo de 16 bits, big-endian."""
        return int.from_bytes(
            frame[offset:offset + 2],
            byteorder="big",
            signed=False,
        )
