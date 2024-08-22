from unittest import TestCase, main, expectedFailure

from ugrd.initramfs_generator import InitramfsGenerator

from zenlib.logging import loggify


@loggify
class TestCpio(TestCase):
    def test_fullauto(self):
        generator = InitramfsGenerator(logger=self.logger, config='tests/fullauto.toml')
        generator.build()

    def test_xz(self):
        generator = InitramfsGenerator(logger=self.logger, config='tests/fullauto.toml', cpio_compression='xz')
        generator.build()

    @expectedFailure
    def test_bad_config(self):
        generator = InitramfsGenerator(logger=self.logger, config='tests/bad_config.toml')
        generator.build()


if __name__ == '__main__':
    main()
