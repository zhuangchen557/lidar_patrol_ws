from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from websockets.asyncio.server import serve

from app.config import settings
from app.rosbridge import RosbridgeClient


async def main() -> None:
    received_operations: list[dict] = []
    received_topics: list[str] = []
    connected = asyncio.Event()
    sensor_message_seen = asyncio.Event()
    command_seen = asyncio.Event()

    async def handler(websocket) -> None:
        async for raw_message in websocket:
            operation = json.loads(raw_message)
            received_operations.append(operation)
            if operation.get("op") == "advertise":
                await websocket.send(
                    json.dumps(
                        {
                            "op": "publish",
                            "topic": "/sensor/temperature",
                            "msg": {"data": 26.5},
                        }
                    )
                )
            if operation.get("op") == "publish" and operation.get("topic") == "/patrol/command":
                assert operation["msg"]["data"] == "start_patrol"
                command_seen.set()

    async def on_status(value: bool) -> None:
        if value:
            connected.set()

    async def on_message(topic: str, message: dict) -> None:
        received_topics.append(topic)
        if topic == "/sensor/temperature" and message.get("data") == 26.5:
            sensor_message_seen.set()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        config = replace(settings, rosbridge_url=f"ws://127.0.0.1:{port}")
        client = RosbridgeClient(config, on_status, on_message)
        client_task = asyncio.create_task(client.run())
        try:
            await asyncio.wait_for(connected.wait(), timeout=5)
            await asyncio.wait_for(sensor_message_seen.wait(), timeout=5)
            assert await client.publish_command("start_patrol") is True
            await asyncio.wait_for(command_seen.wait(), timeout=5)
            assert any(item.get("op") == "subscribe" for item in received_operations)
            assert "/sensor/temperature" in received_topics
        finally:
            await client.stop()
            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

    print("rosbridge subscribe, receive, and command publish smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())
