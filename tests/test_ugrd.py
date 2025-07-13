from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestUGRD(TestCase):
    def test_fullauto(self):
        """Test a basic initramfs image using config determined from the build environment, with no compression."""
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
        generator.build()

    def test_xz(self):
        """Text XZ compression for initramfs."""
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", cpio_compression="xz")
        generator.build()

    def test_zstd(self):
        """Test ZSTD compression for initramfs."""
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", cpio_compression="zstd")
        generator.build()

    def test_bad_config(self):
        """Test that a bad config file which should raise an error."""
        with self.assertRaises(ValueError):
            InitramfsGenerator(logger=self.logger, config="tests/bad_config.toml")

    def test_no_root(self):
        """Test without a rootfs which can be found, should cause the initramfs to restart."""
        generator = InitramfsGenerator(
            logger=self.logger, config="tests/fullauto.toml", test_no_rootfs=True, test_flag="Restarting init"
        )
        generator.build()


if __name__ == "__main__":
    main()
