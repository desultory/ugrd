__version__ = "0.2.0"

from json import loads
from pathlib import Path

from ugrd.exceptions import AutodetectError, ValidationError
from zenlib.util import colorize as c_
from zenlib.util import contains, unset


def _process_net_device(self, net_device: str) -> None:
    """Sets self.net_device to the given net_device."""
    _validate_net_device(self, net_device)
    self.data["net_device"] = net_device
    self["net_device_mac"] = (Path("/sys/class/net") / net_device / "address").read_text().strip()


def _validate_net_device(self, net_device: str) -> None:
    """Validates the given net_device."""
    if not net_device:  # Ensure the net_device is not empty
        if self["net_device_mac"]:
            self.logger.warning(
                f"net_device is empty, using net_device_mac without validation: {c_(self['net_device_mac'], 'yellow')}"
            )
            return None  # Exit early
        raise ValidationError("net_device must not be empty, or net_device_mac must be set.")

    dev_path = Path("/sys/class/net") / net_device
    if not dev_path.exists():  # Ensure the net_device exists on the system
        self.logger.error("Network devices: %s", ", ".join([dev.name for dev in Path("/sys/class/net").iterdir()]))
        raise ValueError("Invalid net_device: {c_(net_device, 'red')}")
    if not (dev_path / "address").exists():
        raise ValueError(f"Invalid net_device, missing MAC address: {c_(net_device, 'red')}")


@contains("hostonly")
def autodetect_net_device_kmods(self) -> None:
    """Autodetects the driver for the net_device."""
    device_path = Path("/sys/class/net") / self["net_device"] / "device"
    if not device_path.exists():
        raise AutodetectError(f"Unable to determine device driver for network device: {c_(self['net_device'], 'red')}")

    driver_path = Path("/sys/class/net") / self["net_device"] / "device" / "driver"
    if driver_path.is_symlink():
        driver_name = driver_path.resolve().name
        self.logger.info(f"Autodetected net_device_driver: {c_(driver_name, 'cyan')}")
        self["kmod_init"] = driver_name
    else:
        raise AutodetectError(f"Unable to determine device driver for network device: {c_(self['net_device'], 'red')}")


@unset("net_device", log_level=40)
@contains("hostonly")
def autodetect_net_device(self) -> None:
    """Sets self.net_device to the device used for the default route with the lowest metric."""
    routes = loads(self._run(["ip", "-j", "r"]).stdout.decode())

    gateways = {}
    for route in routes:
        if route["dst"] == "default":
            gateways[route.get("metric", 0)] = route

    if not gateways:
        raise AutodetectError("No default route found")

    self["net_device"] = gateways[min(gateways.keys())]["dev"]
    self.logger.info(f"Autodetected net_device: {c_(self['net_device'], 'cyan')}")


def resolve_mac(self) -> str:
    """Returns a shell script to resolve a MAC address to a device name"""
    return """
    for dev in /sys/class/net/*; do
        if [ "$(cat $dev/address)" = "$1" ]; then
            printf "%s" "${dev##*/}"
            return
        fi
    done
    rd_fail "Unable to resolve MAC address to device name: $1"
    """
