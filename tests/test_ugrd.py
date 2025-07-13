from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


def bad_function(self):
    """A function that should not be called."""
    return "exit 1"


@loggify
class TestUGRD(TestCase):
    def test_fullauto(self):
        """Test a basic initramfs image using config determined from the build environment, with no compression."""
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
        generator.build()

    def test_bad_config(self):
        """Test that a bad config file which should raise an error."""
        with self.assertRaises(ValueError):
            InitramfsGenerator(logger=self.logger, config="tests/bad_config.toml")

    def test_bad_mask(self):
        """Test that masking a critical function raises an error."""
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
        generator["masks"] = {"init_final": "do_switch_root"}
        with self.assertRaises(RuntimeError):
            generator.build()

    def test_good_mask(self):
        """ Tests that masking a broken function resolves a boot issue. """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
        generator["imports"]["init_main"] += bad_function
        generator["masks"] = {"init_main": "bad_function"}
        generator.build()

    def test_no_root(self):
        """Test without a rootfs which can be found, should cause the initramfs to restart."""
        generator = InitramfsGenerator(
            logger=self.logger, config="tests/fullauto.toml", test_no_rootfs=True, test_flag="Restarting init"
        )
        generator.build()


if __name__ == "__main__":
    main()
