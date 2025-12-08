from unittest import TestCase, main

from pycpio.errors import UnavailableCompression
from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestCompression(TestCase):
    def test_xz(self):
        """Text XZ compression for initramfs."""
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", cpio_compression="xz")
        generator.build()

    def test_zstd(self):
        """Test ZSTD compression for initramfs."""
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", cpio_compression="zstd")
        try:
            generator.build()
        except UnavailableCompression as e:
            self.skipTest(f"ZSTD compression is not available: {e}")


if __name__ == "__main__":
    main()
