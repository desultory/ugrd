from zenlib.util import unset

@unset('lowerdir', "lowerdir is already set, skipping detection.")
def detect_lowerdir(self):
    """Detect the lowerdir using the mounts['root']['destination']"""
    self['lowerdir'] = self.mounts['root']['destination']
    self.logger.info("Detected lowerdir: %s" % self['lowerdir'])


def init_overlayfs(self) -> list[str]:
    """Returns bash lines to create the upperdir and workdir
    Uses /run/upperdir and /run/workdir."""
    return ["edebug $(mkdir -pv /run/upperdir /run/workdir)"]

def mount_overlayfs(self) -> list[str]:
    """Returns bash lines to mount the overlayfs based on the lowerdir"""
    return [
        "einfo $(mount -t overlay overlay -o lowerdir=%s,upperdir=/run/upperdir,workdir=/run/workdir $(readvar SWITCH_ROOT_TARGET))" % self['lowerdir']
    ]



