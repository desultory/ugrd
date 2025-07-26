from pathlib import Path

from zenlib.util import colorize as c_
from zenlib.util import contains

__version__ = "0.2.1"

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
    try:
        with open("/sys/class/dmi/id/product_name", "r") as f:
            self["_dmi_product_name"] = f.read().strip()
    except FileNotFoundError:
        self.logger.warning("Could not read /sys/class/dmi/id/product_name, skipping product name detection.")
        self["_dmi_product_name"] = "Unknown Product"

    try:
        with open("/sys/class/dmi/id/sys_vendor", "r") as f:
            self["_dmi_system_vendor"] = f.read().strip()
    except FileNotFoundError:
        self.logger.warning("Could not read /sys/class/dmi/id/sys_vendor, skipping system vendor detection.")
        self["_dmi_system_vendor"] = "Unknown Vendor"


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


@contains("kmod_autodetect_platform_bus_drivers", "kmod_autodetect_platform_bus_drivers is not enabled, skipping platform bus driver detection.", log_level=10)
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


def _get_platform_mmc_drivers(self, mmc_dev):
    """Helper function to get MMC drivers from a given device.
    Strips the partition number from the device name if present.
    """
    mmc_name = mmc_dev.split("p")[0].replace('blk', '')  # Strip partition number if present, and 'blk' prefix
    mmc_path = Path(f"/sys/class/mmc_host/{mmc_name}/device")
    if not mmc_path.exists():
        self.logger.warning(f"[{c_(mmc_path, 'yellow')}] MMC device path does not exist, skipping detection.")
        return []

    drivers = set()
    if driver := (mmc_path / "driver").resolve().name:
        self.logger.info(f"[{c_(mmc_dev, 'green', bright=True)}] Detected MMC driver: {c_(driver, 'magenta', bright=True)}")
        drivers.add(driver)

    # Check for supplier drivers
    for supplier in mmc_path.iterdir():
        if not supplier.name.startswith("supplier:"):
            continue

        supplier_driver = (supplier / "supplier" / "driver")
        if not supplier_driver.exists():
            self.logger.warning(f"[{c_(mmc_dev, 'yellow', bright=True)}] Supplier driver not found, skipping: {c_(supplier_driver, 'red', bright=True)}")
            continue

        supplier_driver = supplier_driver.resolve()
        self.logger.debug(f"[{c_(mmc_dev, 'green', bright=True)}:{c_(supplier, 'blue')}] Detected MMC supplier driver: {c_(supplier_driver.name, 'magenta', bright=True)}")
        drivers.add(supplier_driver.name)

    return list(drivers)
