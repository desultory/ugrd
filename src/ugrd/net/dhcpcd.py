__version__ = "0.2.1"


from zenlib.util import contains


@contains("net_device", "net_device must be set", raise_exception=True)
def init_dhcpcd(self) -> str:
    """Return shell lines to start dhcpcd"""
    return f"""
    net_device=$(resolve_mac {self.net_device_mac})
    einfo "Starting dhcpcd on: $net_device"
    einfo "dhcpcd output:\n$(dhcpcd "$net_device" 2>&1)"
    """
