from zenlib.util import colorize as c_
from zenlib.util import contains

__version__ = "0.1.1"

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
    """Detects if the system is running in a virtual machine, adds relevant kernel modules to the list.
    Sets the `virtual_machine` attribute to True if a VM is detected, to be used by other modules.
    """
    kmods = set()
    kmods.update(VM_PRODUCT_NAMES.get(self["_dmi_product_name"], []))
    kmods.update(VM_VENDOR_NAMES.get(self["_dmi_system_vendor"], []))

    if kmods:
        self.logger.info(
            f"[{c_(self['_dmi_system_vendor'], color='cyan', bold=True)}]({c_(self['_dmi_product_name'], color='cyan', bright=True)}) Detected VM kmods: {c_((' ').join(kmods), color='magenta', bright=True)}"
        )
        self["virtual_machine"] = True
        self["kmod_init"] = list(kmods)
