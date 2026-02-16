from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestKmod(TestCase):
    def test_kmod_recursion(self):
        """ Check that kernel modules with recursive dependencies don't cause infinite recursion """
        generator = InitramfsGenerator(logger=self.logger, kmod_init=["ipmi_si"],  config="tests/fullauto.toml")
        generator.build()

    def test_no_kmod_bad_kver(self):
        """ Check that the generator doesn't fail if no_kmod is in the config but a kver is passed"""
        generator = InitramfsGenerator(logger=self.logger, config="tests/no_kmods.toml", kernel_version="1.2.0-76-not-real-for-tests-generic")
        generator.build()


if __name__ == "__main__":
    main()
