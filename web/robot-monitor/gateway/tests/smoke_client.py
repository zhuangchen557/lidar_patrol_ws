from __future__ import annotations

import json
from urllib.request import urlopen

from websockets.sync.client import connect


def main() -> None:
    with urlopen("http://127.0.0.1:8000/api/health", timeout=5) as response:
        health = json.load(response)
    assert health["ok"] is True
    assert health["gateway"] == "online"

    with connect("ws://127.0.0.1:8000/ws/robot", open_timeout=5) as websocket:
        bridge_status = json.loads(websocket.recv(timeout=5))
        robot_status = json.loads(websocket.recv(timeout=5))
        assert bridge_status["type"] == "bridge_status"
        assert robot_status["type"] == "robot_status"

        websocket.send(json.dumps({"type": "auth", "password": "not-configured"}))
        auth_result = json.loads(websocket.recv(timeout=5))
        assert auth_result["type"] == "auth_result"
        assert auth_result["ok"] is False

    print("FastAPI HTTP and WebSocket smoke test passed")


if __name__ == "__main__":
    main()
