#!/usr/bin/env bash
# ============================================================
# 推车建图 v3 — Plan B: 纯扫描匹配, 不依赖 rf2o
# ============================================================
# 链路: 雷达(/scan 变长) → scan_repacker(/scan_fixed 固定360点)
#       → slam_toolbox(纯扫描匹配, map→odom)
#       + 静态 identity odom→base_link (不用 rf2o, 消除 TF 竞争)
#
# 原理: slam_toolbox 的 scan matcher 从零开始估计位姿, 不依赖里程计.
#       push-mapping 速度慢(<=0.3m/s), 扫描匹配窗口(0.25m)完全够用.
#
# 用法:
#   bash ~/slam_config/handheld_mapping.sh          # 启动
#   bash ~/slam_config/handheld_mapping.sh --stop   # 停止
# ============================================================
source /opt/ros/humble/setup.bash
source ~/lidar_ws/install/setup.bash
source ~/rf2o_ws/install/setup.bash 2>/dev/null

MAP_PARAMS=/home/zhuangchen557/slam_config/mapper_params_online_async.yaml

stop_all() {
  echo "=== 停止所有节点(含孤儿) ==="
  pkill -f "rf2o_laser_odometry" 2>/dev/null
  pkill -f "async_slam_toolbox" 2>/dev/null
  pkill -f "ldlidar" 2>/dev/null
  pkill -f "static_transform_publisher" 2>/dev/null
  pkill -f "scan_repacker" 2>/dev/null
  echo "已停止"
}

watchdog() {
  while true; do
    sleep 5
    if ! pgrep -f "ldlidar" >/dev/null 2>&1; then
      if [ -e /dev/wheeltec_lidar ]; then
        echo "[watchdog] ldlidar 挂了但设备在，重启..."
        nohup ros2 launch ldlidar ld06.launch.py > /tmp/hm_lidar.log 2>&1 &
      fi
    fi
  done
}

if [ "$1" = "--stop" ]; then stop_all; exit 0; fi

stop_all
sleep 1

echo "=== [1/5] 激光雷达 (自带 base_link→laser z=0.18) ==="
ros2 launch ldlidar ld06.launch.py > /tmp/hm_lidar.log 2>&1 &
watchdog &
sleep 6

echo "=== [2/5] scan_repacker (/scan → /scan_fixed 固定360点) ==="
python3 /home/zhuangchen557/slam_config/scan_repacker.py > /tmp/hm_repacker.log 2>&1 &
sleep 2

echo "=== [3/5] 静态 identity odom→base_link (Plan B: 不用 rf2o) ==="
ros2 run tf2_ros static_transform_publisher \
  0 0 0 0 0 0 1 odom base_link \
  > /tmp/hm_static_odom.log 2>&1 &
sleep 2

echo "=== [4/5] slam_toolbox (纯扫描匹配建图) ==="
ros2 launch slam_toolbox online_async_launch.py \
  slam_params_file:=$MAP_PARAMS use_sim_time:=false \
  > /tmp/hm_slam.log 2>&1 &

echo ""
echo "=== [5/5] 自检 (8s) ==="
sleep 8
echo "--- /scan_fixed 频率 ---"
timeout 3 ros2 topic hz /scan_fixed 2>/dev/null | grep average || echo "!! /scan_fixed 无数据"
echo "--- TF 链 ---"
timeout 3 ros2 topic echo /tf --once 2>/dev/null | head -15 || echo "!! 无 TF"
timeout 3 ros2 topic echo /tf_static --once 2>/dev/null | grep frame_id | head -3
echo "--- slam 日志 ---"
tail -3 /tmp/hm_slam.log 2>/dev/null
echo "--- repacker ---"
tail -2 /tmp/hm_repacker.log 2>/dev/null

echo ""
echo ">>> 查看地图: rviz2 → Fixed Frame=map, Add Map(/map)+LaserScan(/scan_fixed)"
echo ">>> 推车 <=0.3m/s, 盯 RViz 看墙壁是否对齐"
echo ">>> 保存: ros2 run nav2_map_server map_saver_cli -f ~/my_map"
echo ">>> 结束: bash ~/slam_config/handheld_mapping.sh --stop"

trap 'stop_all; exit 0' INT TERM
while true; do sleep 10; done
