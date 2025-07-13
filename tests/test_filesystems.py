from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from ugrd.kmod import MissingModuleError
from zenlib.logging import loggify


@loggify
class TestFilesystems(TestCase):
    def test_ext4(self):
        """ Test ext4 root filesystem functionality. """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/ext4.toml")
        generator.build()

    def test_btrfs(self):
        """ Test btrfs root filesystem functionality. """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/btrfs.toml")
        generator.build()

    def test_xfs(self):
        """ Test xfs root filesystem functionality. """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/xfs.toml")
        generator.build()

    def test_f2fs(self):
        """ Test f2fs root filesystem functionality. """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/f2fs.toml")
        try:
            generator.build()
        except MissingModuleError:
            generator.logger.critical("F2FS is not supported on this system, skipping test.")

    def test_overlayfs(self):
        """ Test overlayfs/tmpfs overlay over root creation. """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/overlayfs.toml")
        generator.build()

    def test_squashfs(self):
        """ Test squashfs/overlayfs/tmpfs for live cd systems. """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fs/squashfs.toml")
        generator.build()

if __name__ == "__main__":
    main()
