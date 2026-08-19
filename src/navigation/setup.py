from setuptools import setup

package_name = "navigation"

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name, "backend"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    entry_points={
        "console_scripts": [
            "waypoint_recorder=navigation.waypoint_recorder:main",
            "waypoint_player=navigation.waypoint_player:main",
            "route_validator=navigation.route_validator:main",
            "rosbridge_client=navigation.rosbridge_client:main",
        ],
    },
)
