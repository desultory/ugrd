from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestCpio(TestCase):
    def test_ext4(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/ext4.toml")
        generator.build()

    def test_btrfs(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/btrfs.toml")
        generator.build()

    def test_xfs(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/xfs.toml")
        generator.build()


if __name__ == "__main__":
    main()
