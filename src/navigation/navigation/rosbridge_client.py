#!/usr/bin/env python3
"""
Minimal rosbridge WebSocket client.

This is a verification tool for the team's rosbridge_server on port 9090.
It can subscribe to /odom and print received messages.
"""

import argparse
import json

try:
    import websocket
except ImportError:
    websocket = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://localhost:9090")
    parser.add_argument("--topic", default="/odom")
    args = parser.parse_args()

    if websocket is None:
        raise SystemExit(
            "缺少 websocket-client，请执行: pip install websocket-client"
        )

    ws = websocket.create_connection(args.url, timeout=5)
    ws.send(json.dumps({
        "op": "subscribe",
        "topic": args.topic,
        "type": "nav_msgs/msg/Odometry",
        "throttle_rate": 200,
        "queue_length": 1,
    }))

    print(f"已连接 {args.url}，正在监听 {args.topic}")
    try:
        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("op") == "publish":
                print(json.dumps(msg.get("msg", {}), ensure_ascii=False))
    except KeyboardInterrupt:
        pass
    finally:
        ws.close()


if __name__ == "__main__":
    main()
