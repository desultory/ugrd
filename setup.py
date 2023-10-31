from setuptools import setup
from ugrd.initramfs_generator import __version__ as version


setup(
    name="ugrd",
    version=version,
    description="A simple initramfs generator",
    author="desultory",
    package_data={
        "ugrd": ["*/*.toml",
                 "include/gen_init_cpio.c"]
    },
    entry_points={
        "console_scripts": [
            "ugrd = ugrd.main:main"
        ]
    }
)
