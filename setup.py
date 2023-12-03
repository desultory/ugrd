from setuptools import setup
from ugrd.initramfs_generator import __version__ as version


setup(
    name="ugrd",
    version=version,
    description="A simple initramfs generator",
    author="desultory",
    package_data={
        "ugrd": ["*/*.toml"]
    },
    install_requires=['zenlib>=1.2.0', 'pycpio>=0.5.0'],
    entry_points={
        "console_scripts": [
            "ugrd = ugrd.main:main"
        ]
    }
)
