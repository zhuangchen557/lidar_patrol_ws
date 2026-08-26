#!/usr/bin/env bash
# 扫描流健康检查: 采样30帧, 统计每帧点数与帧间隔
source /opt/ros/humble/setup.bash
source ~/lidar_ws/install/setup.bash

pkill -f static_transform_publisher 2>/dev/null; pkill -f ldlidar 2>/dev/null; sleep 1
ros2 launch ldlidar ld06.launch.py > /tmp/diag_lidar.log 2>&1 &
sleep 6

echo "=== 采样 /scan (15秒) ==="
timeout 15 ros2 topic echo /scan --no-arr 2>/dev/null > /tmp/scan_raw.txt
python3 - <<'EOF'
import re
txt = open('/tmp/scan_raw.txt').read()
scans = re.findall(r'sec: (\d+)\n\s*nanosec: (\d+)', txt)
lens = [int(m) for m in re.findall(r'ranges_len: (\d+)', txt)]
print(f"帧数: {len(lens)}")
if lens:
    print(f"点数: min={min(lens)} max={max(lens)} 平均={sum(lens)/len(lens):.0f}")
    from collections import Counter
    buckets = Counter((n//50)*50 for n in lens)
    print("点数分布:", dict(sorted(buckets.items())))
if len(scans) >= 3:
    times = [int(s) + int(n)/1e9 for s, n in scans]
    gaps = [times[i+1]-times[i] for i in range(len(times)-1)]
    print(f"帧间隔: min={min(gaps)*1000:.0f}ms max={max(gaps)*1000:.0f}ms")
    print(f"间隔>200ms(突发延迟)次数: {sum(1 for g in gaps if g > 0.2)}")
EOF
