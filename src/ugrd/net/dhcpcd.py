__version__ = "0.3.0"


from zenlib.util import contains


@contains("net_device", "net_device must be set", raise_exception=True)
def init_dhcpcd(self) -> str:
    """Return shell lines to start dhcpcd, persisting the interface config on exit."""
    return f"""
    net_device=$(resolve_mac {self.net_device_mac})
    einfo "Starting dhcpcd on: $net_device"
    einfo "dhcpcd output:\n$(dhcpcd -p "$net_device" 2>&1)"
    """


@contains("dhcpcd_stop")
def stop_dhcpcd(self) -> str:
    """Return shell lines to stop dhcpcd, without releasing the lease."""
    return f"""
    net_device=$(resolve_mac {self.net_device_mac})
    einfo "Stopping dhcpcd on $net_device: $(dhcpcd -x "$net_device" 2>&1)"
    """
