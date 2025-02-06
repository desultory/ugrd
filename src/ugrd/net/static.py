__version__ = "0.2.0"

from json import loads

from zenlib.util import colorize, contains, unset

from .. import AutodetectError


@unset("ip_gateway")
@contains("autodetect_gateway")
@contains("hostonly")
def autodetect_gateway(self):
    """Detects the default route and sets ip_gateway accordingly.
    Returns the device name of the default route.
    """
    routes = loads(self._run(["ip", "-j", "r"]).stdout.decode())

    for route in routes:
        if route["dev"] == self["net_device"]:
            self["ip_gateway"] = route["gateway"]
            return self.logger.info(
                "[%s] Detected gateway: %s", colorize(self["net_device"], "blue"), colorize(self["ip_gateway"], "cyan")
            )
    else:
        raise AutodetectError("No default route found")


@unset("ip_address")
@contains("autodetect_ip")
@contains("hostonly")
def autodetect_ip(self):
    """Autodetects the ip address of the network device if not already set."""
    device_info = loads(self._run(["ip", "-d", "-j", "a", "show", self["net_device"]]).stdout.decode())[0]
    if "vlan" == device_info.get("linkinfo", {}).get("info_kind"):  # enable the VLAN module to handle vlans
        self.logger.info("[%s] VLAN detected, enabling the VLAN module.", colorize(self["net_device"], "blue"))
        self["modules"] = "ugrd.net.vlan"
    ip_addr = device_info["addr_info"][0]["local"]
    ip_cidr = device_info["addr_info"][0]["prefixlen"]
    self["ip_address"] = f"{ip_addr}/{ip_cidr}"
    self.logger.info(
        "[%s] Detected ip address: %s", colorize(self["net_device"], "blue"), colorize(self["ip_address"], "cyan")
    )


@contains("ip_address", "ip_address must be set", raise_exception=True)
@contains("ip_gateway", "ip_gateway must be set", raise_exception=True)
@contains("net_device", "net_device must be set", raise_exception=True)
def init_net(self) -> str:
    """Returns shell lines to initialize the network device.
    Skips the initialization if the device is already up, and there is a gateway on the device.
    """
    return f"""
    net_device=$(resolve_mac {self.net_device_mac})
    if ip link show "$net_device" | grep -q 'UP,' && ip route show | grep -q "default via .* dev $net_device"; then
        ewarn "Network device is already up, skipping: $net_device"
        return
    fi
    einfo "Configuring network device: $net_device"
    ip link set "$net_device" up
    ip addr add {self.ip_address} dev "$net_device"
    ip route add default via {self.ip_gateway}
    """
