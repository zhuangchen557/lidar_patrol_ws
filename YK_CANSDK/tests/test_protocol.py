from __future__ import annotations

import unittest

from yk_can_sdk.protocol import (
    CanFrame,
    CanStreamParser,
    Fault,
    ParameterAck,
    SpeedFeedback,
    ThermalFaultFeedback,
    build_motor_frame,
    build_parameter_write_frame,
    decode_feedback,
    yk_can_id,
)


class ProtocolTests(unittest.TestCase):
    def test_workbook_forward_vector(self) -> None:
        packet = build_motor_frame(1, 100, -100).to_gateway_bytes()
        self.assertEqual(packet.hex(" ").upper(), "88 0D EE 01 00 00 00 00 64 FF FF FF 9C")

    def test_signed_motor_vector(self) -> None:
        packet = build_motor_frame(2, -200, 200).to_gateway_bytes()
        self.assertEqual(packet.hex(" ").upper(), "88 0D EE 02 00 FF FF FF 38 00 00 00 C8")

    def test_parameter_write_and_forbidden_registers(self) -> None:
        frame = build_parameter_write_frame(1, 0x0028, 2)
        self.assertEqual(frame.to_gateway_bytes().hex(" ").upper(), "88 0D EE 01 0A 83 00 28 00 00 02 00 00")
        with self.assertRaises(ValueError):
            build_parameter_write_frame(1, 0x0026, 1)

    def test_fragmented_coalesced_and_resynchronized_stream(self) -> None:
        one = CanFrame(yk_can_id(1, 0x01), (10).to_bytes(4, "big", signed=True) + (-10).to_bytes(4, "big", signed=True)).to_gateway_bytes()
        two = CanFrame(yk_can_id(2, 0x01), (20).to_bytes(4, "big", signed=True) + (-20).to_bytes(4, "big", signed=True)).to_gateway_bytes()
        parser = CanStreamParser()
        self.assertEqual(parser.feed(b"noise" + one[:5]), [])
        frames = parser.feed(one[5:] + two)
        self.assertEqual([frame.driver_id for frame in frames], [1, 2])
        self.assertEqual(parser.discarded_bytes, 5)

    def test_speed_feedback(self) -> None:
        frame = CanFrame(yk_can_id(1, 0x01), (-50).to_bytes(4, "big", signed=True) + (75).to_bytes(4, "big", signed=True))
        result = decode_feedback(frame, received_monotonic=12.5)
        self.assertIsInstance(result, SpeedFeedback)
        self.assertEqual((result.motor1, result.motor2), (-50, 75))
        self.assertEqual(result.received_monotonic, 12.5)

    def test_fault_feedback(self) -> None:
        payload = (455).to_bytes(2, "big", signed=True) + (460).to_bytes(2, "big", signed=True)
        payload += (Fault.STALL | Fault.HALL_ABNORMAL).to_bytes(2, "big") + (0).to_bytes(2, "big")
        result = decode_feedback(CanFrame(yk_can_id(2, 0x03), payload))
        self.assertIsInstance(result, ThermalFaultFeedback)
        self.assertEqual(result.motor1_temperature_c, 45.5)
        self.assertTrue(result.has_fault)
        self.assertIn("堵转", result.motor1_faults.labels_zh)

    def test_parameter_ack(self) -> None:
        data = bytes.fromhex("83 00 28 00 00 02 00 00")
        result = decode_feedback(CanFrame(yk_can_id(1, 0x0B), data))
        self.assertIsInstance(result, ParameterAck)
        self.assertEqual((result.register, result.value), (0x0028, 2))


if __name__ == "__main__":
    unittest.main()

