__version__ = '0.2.0'


def md_init(self):
    return """
    export MDADM_NO_UDEV=1
    einfo "Assembling MD devices: $(mdadm --assemble --scan 2>&1)"
    """
