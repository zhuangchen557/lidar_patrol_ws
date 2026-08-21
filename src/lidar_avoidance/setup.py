from setuptools import setup

package_name = 'lidar_avoidance'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch',
         ['launch/avoidance_test.launch.py']),
        ('share/' + package_name + '/config',
         ['config/avoidance.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={
        'console_scripts': [
            'laser_avoidance = lidar_avoidance.laser_avoidance:main',
        ],
    },
)
