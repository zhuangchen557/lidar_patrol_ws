from __future__ import annotations

import socket
import threading
import unittest

from yk_can_sdk import GatewayClient, NetworkConfig
from yk_can_sdk.protocol import CanFrame, build_motor_frame, yk_can_id


class OneShotGateway:
    def __init__(self) -> None:
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.received = bytearray()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.close()
        self.thread.join(timeout=1.0)

    def _run(self) -> None:
        try:
            conn, _address = self.server.accept()
            with conn:
                while len(self.received) < 13:
                    chunk = conn.recv(13 - len(self.received))
                    if not chunk:
                        return
                    self.received.extend(chunk)
                feedback = CanFrame(
                    yk_can_id(1, 0x01),
                    (123).to_bytes(4, "big", signed=True) + (-123).to_bytes(4, "big", signed=True),
                ).to_gateway_bytes()
                conn.sendall(feedback[:4])
                conn.sendall(feedback[4:])
        except OSError:
            return


class ClientIntegrationTests(unittest.TestCase):
    def test_local_tcp_roundtrip_with_fragmented_feedback(self) -> None:
        gateway = OneShotGateway()
        gateway.start()
        client = GatewayClient(
            NetworkConfig("127.0.0.1", gateway.port, connect_timeout_s=1.0, receive_timeout_s=0.05)
        )
        try:
            client.connect()
            client.send_frame(build_motor_frame(1, 0, 0))
            telemetry = client.wait_for_feedback(1, timeout_s=1.0)
            self.assertIsNotNone(telemetry)
            self.assertIsNotNone(telemetry.speed if telemetry else None)
            self.assertEqual(
                (telemetry.speed.motor1, telemetry.speed.motor2),  # type: ignore[union-attr]
                (123, -123),
            )
            self.assertEqual(bytes(gateway.received), build_motor_frame(1, 0, 0).to_gateway_bytes())
        finally:
            client.close()
            gateway.close()


if __name__ == "__main__":
    unittest.main()
