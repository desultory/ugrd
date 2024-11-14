from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestCpio(TestCase):
    def test_ext4(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/ext4.toml")
        generator.build()

    def test_btrfs(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/btrfs.toml")
        generator.build()

    def test_xfs(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/xfs.toml")
        generator.build()

    def test_overlayfs(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/overlayfs.toml")
        generator.build()

    def test_squashfs(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/squashfs.toml")
        generator.build()

if __name__ == "__main__":
    main()
