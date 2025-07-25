from pathlib import Path

from zenlib.util import colorize as c_
from zenlib.util import contains

__version__ = "0.2.0"

VM_PRODUCT_NAMES = {
    "Virtual Machine": ["virtio_blk"],
    "Parallels ARM Virtual Machine": ["virtio_blk"],
    "Standard PC (Q35 + ICH9, 2009)": ["virtio_blk"],
}

VM_VENDOR_NAMES = {
    "Microsoft Corporation": ["hv_storvsc"],
    "VMware, Inc.": ["vmw_pvscsi"],
    "Xen": ["xen_blk"],
    "QEMU": ["virtio_blk"],
    "Parallels International GmbH.": ["virtio_blk"],
}


@contains("hostonly", "hostonly is not enabled, skipping platform detection.", log_level=30)
def get_platform_info(self):
    """Detects plaform information such as the vendor and product name"""
    with open("/sys/class/dmi/id/product_name", "r") as f:
        self["_dmi_product_name"] = f.read().strip()

    with open("/sys/class/dmi/id/sys_vendor", "r") as f:
        self["_dmi_system_vendor"] = f.read().strip()


@contains("hostonly", "hostonly is not enabled, skipping VM detection.", log_level=30)
def autodetect_virtual_machine(self):
    """Detects if the system is running in a virtual machine, using DMI information.
    Uses the system vendor to add required kmods
    uses the product name to add additional kmods.

    Sets the `virtual_machine` attribute to True if a VM is detected, to be used by other modules.
    """
    vendor_kmods = VM_VENDOR_NAMES.get(self["_dmi_system_vendor"], [])
    product_kmods = VM_PRODUCT_NAMES.get(self["_dmi_product_name"], [])
    kmods = set(vendor_kmods + product_kmods)

    if kmods:
        self.logger.info(
            f"[{c_(self['_dmi_system_vendor'], color='cyan', bold=True)}]({c_(self['_dmi_product_name'], color='cyan', bright=True)}) Detected VM kmods: {c_((' ').join(kmods), color='magenta', bright=True)}"
        )
        self["virtual_machine"] = True
        if vendor_kmods:
            self["kmod_init"] = vendor_kmods
        if product_kmods:
            self["_kmod_auto"] = product_kmods

@contains("hostonly", "hostonly is not enabled, skipping regulator driver detection.", log_level=30)
def autodetect_regulator_drivers(self):
    """ Detects regulator drivers from /sys/class/regulator and adds them to the _kmod_auto list."""
    regulators_path = Path("/sys/class/regulator")
    if not regulators_path.exists():
        self.logger.warning(f"[{c_(regulators_path, 'yellow')}] Regulator path does not exist, skipping detection.")
        return

    kmods = set()

    for regulator in regulators_path.iterdir():
        if regulator.is_dir() and (regulator / "device").exists():
            name = (regulator / "name").read_text().strip() if (regulator / "name").exists() else regulator.name
            driver = (regulator / "device" / "driver").resolve().name
            kmods.add(driver)
            self.logger.debug(f"[{c_(name, 'cyan', bright=True)}] Detected regulator driver: {c_(driver, 'magenta', bright=True)}")

    if not kmods:
        self.logger.info("No regulator drivers detected.")
    else:
        self.logger.info(f"Detected regulator drivers: {c_(', '.join(kmods), color='magenta', bright=True)}")
        self["_kmod_auto"] = list(kmods)


@contains("hostonly", "hostonly is not enabled, skipping platform bus driver detection.", log_level=30)
def autodetect_platform_bus_drivers(self):
    """ Reads drivers from /sys/bus/platform/drivers and adds them to the _kmod_auto list."""

    drivers_path = Path("/sys/bus/platform/drivers")
    if not drivers_path.exists():
        self.logger.warning(f"[{c_(drivers_path, 'yellow')}] Platform bus drivers path does not exist, skipping detection.")
        return

    drivers = [driver.name for driver in drivers_path.iterdir() if driver.is_dir()]
    if drivers:
        self["_kmod_auto"] = list(set(self.get("_kmod_auto", []) + drivers))
        self.logger.info(f"Detected platform bus drivers: {c_(', '.join(drivers), color='magenta', bright=True)}")
    else:
        self.logger.info("No platform bus drivers detected.")

