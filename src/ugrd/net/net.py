__version__ = "0.1.1"

from json import loads
from pathlib import Path

from zenlib.util import colorize, contains, unset

from ugrd import AutodetectError


def _process_net_device(self, net_device: str):
    """Sets self.net_device to the given net_device."""
    _validate_net_device(self, net_device)
    self.data["net_device"] = net_device
    self["net_device_mac"] = (Path("/sys/class/net") / net_device / "address").read_text().strip()


def _validate_net_device(self, net_device: str):
    """Validates the given net_device."""
    if not net_device:  # Ensure the net_device is not empty
        if self["net_device_mac"]:
            return self.logger.warning("net_device is empty, using net_device_mac without validation: %s" % self["net_device_mac"])
        raise ValueError("net_device must not be empty")

    dev_path = Path("/sys/class/net") / net_device
    if not dev_path.exists():  # Ensure the net_device exists on the system
        self.logger.error("Network devices: %s", ", ".join([dev.name for dev in Path("/sys/class/net").iterdir()]))
        raise ValueError("Invalid net_device: %s" % net_device)
    if not (dev_path / "address").exists():
        raise ValueError("Invalid net_device, missing MAC address: %s" % net_device)


@contains("hostonly")
def autodetect_net_device_kmods(self):
    """Autodetects the driver for the net_device."""
    device_path = Path("/sys/class/net") / self["net_device"] / "device"
    if not device_path.exists():
        raise AutodetectError("Unable to determine device driver for device: %s" % self["net_device"])

    driver_path = Path("/sys/class/net") / self["net_device"] / "device" / "driver"
    if driver_path.is_symlink():
        driver_name = driver_path.resolve().name
        self.logger.info("Autodetected net_device_driver: %s" % colorize(driver_name, "cyan"))
        self["kmod_init"] = driver_name
    else:
        raise AutodetectError("Unable to determine device driver for device: %s" % self["net_device"])


@unset("net_device", log_level=40)
@contains("hostonly")
def autodetect_net_device(self):
    """Sets self.net_device to the device used for the default route with the lowest metric."""
    routes = loads(self._run(["ip", "-j", "r"]).stdout.decode())

    gateways = {}
    for route in routes:
        if route["dst"] == "default":
            gateways[route["metric"]] = route

    if not gateways:
        raise AutodetectError("No default route found")

    self["net_device"] = gateways[min(gateways.keys())]["dev"]
    self.logger.info("Autodetected net_device: %s" % colorize(self["net_device"], "cyan"))


def resolve_mac(self):
    """Returns a shell script to resolve a MAC address to a deviec name"""
    return """
    for dev in /sys/class/net/*; do
        if [ "$(cat $dev/address)" == "$1" ]; then
            printf "%s" "${dev##*/}"
            return
        fi
    done
    rd_fail "Unable to resolve MAC address to device name: $1"
    """
