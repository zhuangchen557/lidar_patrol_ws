from setuptools import setup
import os
from glob import glob

package_name = "vehicle_bringup"

setup(
    name=package_name,
    version="0.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "config", "maps"), glob("config/maps/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    entry_points={
        "console_scripts": [
            "chassis_node = vehicle_bringup.chassis_node:main",
            "scan_repacker = vehicle_bringup.scan_repacker:main",
            "sensor_bridge_node = vehicle_bringup.sensor_bridge_node:main",
    "scan_repub = vehicle_bringup.scan_repub:main",
    "particle_bridge = vehicle_bringup.particle_bridge:main",
        ],
    },
)
