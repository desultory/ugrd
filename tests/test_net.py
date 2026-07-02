from unittest import TestCase, main
from os import fsdecode

from ugrd.initramfs_generator import InitramfsGenerator
from ugrd.kmod.kmod import _get_kmod_info, DependencyResolutionError
from ugrd.exceptions import ValidationError

from zenlib.logging import loggify
from zenlib.util import colorize as c_


def pull_test_network_kmod(self):
    """ Gets the first available network driver kmod
    If test_netdev is defined, checks it is valid
    """
    drivers =  fsdecode(self._run([f"qemu-system-{self['test_arch']}", '-nic', 'model=help']).stdout).split("\n")

    if self["test_netdev"] and self["test_netdev"] not in drivers:
        raise ValidationError(f"Defined test_netdev is not a valid qemu network device model: {c_(self['test_netdev'], 'red')}")
    for driver in drivers[1:]:
        try:
            _get_kmod_info(self, driver)
            self.logger.log(33, f"Using virtual network driver for testing: {c_(driver, 'cyan')}")
            self["_kmod_auto"] = driver
            self["test_netdev"] = driver
            return
        except DependencyResolutionError:
            self.logger.debug(f"Could not find network driver for testing: {c_(driver, 'yellow')}")

@loggify
class TestNetwork(TestCase):
    def test_static_network(self):
        """ Tests static network config
        The test will time out if it cannot find/configure the interface with the autodetected MAC address
        """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", modules="ugrd.net.static")
        generator["imports"]["build_enum"] += pull_test_network_kmod
        generator["import_order"]["after"]["autodetect_modules"] = "pull_test_network_kmod"
        generator.build()

    def test_dhcpcd(self):
        """ Tests the dhcpcd module
        Times out similarly to the static network test
        """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", modules="ugrd.net.dhcpcd")
        generator["imports"]["build_enum"] += pull_test_network_kmod
        generator["import_order"]["after"]["autodetect_modules"] = "pull_test_network_kmod"
        generator.build()


if __name__ == "__main__":
    main()
