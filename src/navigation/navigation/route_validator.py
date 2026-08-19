#!/usr/bin/env python3
"""Validate a patrol route before running it."""

import json
import math
import sys


def validate(path):
    with open(path, "r", encoding="utf-8") as f:
        route = json.load(f)

    errors = []
    if route.get("frame_id", "map") != "map":
        errors.append("frame_id 必须为 map")

    points = route.get("points")
    if not isinstance(points, list) or not points:
        errors.append("points 必须是非空数组")
        return errors

    ids = set()
    for i, p in enumerate(points, start=1):
        for key in ("id", "x", "y", "yaw", "label"):
            if key not in p:
                errors.append(f"第{i}个点缺少 {key}")
        if "id" in p:
            if p["id"] in ids:
                errors.append(f"巡检点 id 重复: {p['id']}")
            ids.add(p["id"])
        for key in ("x", "y", "yaw"):
            if key in p and not isinstance(p[key], (int, float)):
                errors.append(f"第{i}个点 {key} 不是数字")
        if "yaw" in p and isinstance(p["yaw"], (int, float)):
            if not math.isfinite(p["yaw"]):
                errors.append(f"第{i}个点 yaw 非有限数")

    return errors


def main():
    if len(sys.argv) != 2:
        print("用法: python3 route_validator.py routes/route.json")
        return 2

    errors = validate(sys.argv[1])
    if errors:
        print("路线校验失败：")
        for e in errors:
            print(f"- {e}")
        return 1

    print("路线校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
