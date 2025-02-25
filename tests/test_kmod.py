from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestKmod(TestCase):
    def test_kmod_recursion(self):
        """ Check that kernel modules with recursive dependencies don't cause infinite recursion """
        generator = InitramfsGenerator(logger=self.logger, kmod_init=["ipmi_si"],  config="tests/fullauto.toml")
        generator.build()


if __name__ == "__main__":
    main()
