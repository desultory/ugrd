__version__ = '0.1.2'


def md_init(self):
    return 'einfo "Assembling MD devices: $(mdadm --assemble --scan 2>&1)"'
