from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator

from zenlib.logging import loggify


@loggify
class TestCpio(TestCase):
    def test_fullauto(self):
        generator = InitramfsGenerator(logger=self.logger, config='fullauto.toml')
        generator.build()


if __name__ == '__main__':
    main()
