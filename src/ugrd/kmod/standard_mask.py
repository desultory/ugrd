__version__ = "0.1.0"

def add_kmod_masks(self):
    """Adds kmod masks based on the ignore settings:
        - kmod_ignore_video: ugrd.fs.novideo
        - kmod_ignore_sound: ugrd.fs.nosound
        - kmod_ignore_network: ugrd.fs.nonetwork
    """
    for ignore in ["video", "sound", "network"]:
        if getattr(self, f"kmod_ignore_{ignore}", False):
            self["modules"] = f"ugrd.kmod.no{ignore}"
