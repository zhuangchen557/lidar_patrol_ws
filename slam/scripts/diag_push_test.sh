#!/usr/bin/env bash
# 推车里程计诊断 v3: 20秒推车窗口, 每2秒采样打印累计位移轨迹
# 用法: bash ~/slam_config/diag_push_test.sh
source /opt/ros/humble/setup.bash
source ~/lidar_ws/install/setup.bash
source ~/rf2o_ws/install/setup.bash

echo "=== [1] 检查雷达连接 ==="
if [ ! -e /dev/wheeltec_lidar ]; then
  echo "!! /dev/wheeltec_lidar 不存在, 先插雷达 USB 并 usbipd attach"
  exit 1
fi
echo "OK: /dev/wheeltec_lidar 存在"

echo "=== [2] 重启 雷达+rf2o (清零里程计) ==="
pkill -f rf2o_laser_odometry 2>/dev/null; pkill -f ldlidar 2>/dev/null; sleep 1
ros2 launch ldlidar ld06.launch.py > /tmp/diag_lidar.log 2>&1 &
sleep 6
ros2 run rf2o_laser_odometry rf2o_laser_odometry_node \
  --ros-args --params-file ~/slam_config/rf2o_params.yaml > /tmp/diag_rf2o.log 2>&1 &
sleep 5

echo "=== [3] /scan 频率 ==="
timeout 4 ros2 topic hz /scan 2>/dev/null | grep -m1 average || echo "!! /scan 无数据"

echo "=== [4] 推车 20 秒 (匀速直线 3~5 米) ==="
echo ">>> 准备... 3 秒后开始推, 匀速直线!"
sleep 3
for i in $(seq 1 10); do
  t=$((i * 2))
  ros2 topic echo /odom_rf2o --once --field pose.pose.position 2>/dev/null > /tmp/diag_s.txt
  python3 - "$t" <<'EOF'
import re, sys
t = open('/tmp/diag_s.txt').read()
x = float(re.search(r'x: ([-\d.e+]+)', t).group(1))
y = float(re.search(r'y: ([-\d.e+]+)', t).group(1))
print(f"  t={sys.argv[1]}s: 累计位移 {((x*x+y*y)**0.5):.2f} m  (x={x:.2f}, y={y:.2f})")
EOF
  sleep 2
done

echo "=== [5] rf2o 日志尾部 ==="
tail -4 /tmp/diag_rf2o.log
echo ">>> 判读: 位移应随推车稳步增长到 3~5m; 若中途停滞不动 = rf2o 卡死"
