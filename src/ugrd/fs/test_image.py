__version__ = "1.3.0"

from tempfile import TemporaryDirectory

from zenlib.util import colorize as c_
from zenlib.util import contains


@contains("test_flag", "A test flag must be set to create a test image", raise_exception=True)
def init_banner(self):
    """Initialize the test image banner, set a random flag if not set."""
    self["banner"] = f"echo {self['test_flag']}"


def _allocate_image(self, image_path, padding=0):
    """Allocate the test image size"""
    self._mkdir(image_path.parent, resolve_build=False)  # Make sure the parent directory exists
    if image_path.exists():
        if self.clean:
            self.logger.warning("Removing existing filesystem image file: %s" % c_(image_path, "red"))
            image_path.unlink()
        else:
            raise Exception("File already exists and 'clean' is off: %s" % c_(image_path, "red", bold=True))

    with open(image_path, "wb") as f:
        self.logger.info("Allocating test image file: %s" % c_(f.name, "green"))
        f.write(b"\0" * (self.test_image_size + padding) * 2**20)

def _copy_fs_contents(self, image_path, build_dir):
    """ Mount and copy the filesystem contents into the image,
    for filesystems which cannot be created directly from a directory"""
    try:
        with TemporaryDirectory() as tmp_dir:
            self._run(["mount", image_path, tmp_dir])
            self._run(["cp", "-a", f"{build_dir}/.", tmp_dir])
            self._run(["umount", tmp_dir])
    except RuntimeError as e:
        raise RuntimeError("Could not mount the test image: %s", e)


def _get_luks_config(self):
    """Gets the LUKS configuration from the passed cryptsetup config using _cryptsetup_root as the key,
    if not found, uses the first defined luks device if there is only one, otherwise raises an exception"""
    if dev := self["cryptsetup"].get(self["_cryptsetup_root"]):
        return dev
    if len(self["cryptsetup"]) == 1:
        return next(iter(self["cryptsetup"].values()))
    raise ValueError("Could not find a LUKS configuration")


def _get_luks_uuid(self):
    """Gets the uuid from the cryptsetup root config"""
    return _get_luks_config(self).get("uuid")


def _get_luks_keyfile(self):
    """Gets the luks keyfile the cryptsetup root config,
    if not defined, generates a keyfile using the banner"""
    config = _get_luks_config(self)
    if keyfile := config.get("key_file"):
        return keyfile
    raise ValueError("No LUKS key_file is set.")


def make_test_luks_image(self, image_path):
    """Creates a LUKS image to hold the test image"""
    try:
        self._run(["cryptsetup", "status", "test_image"], fail_silent=True)  # Check if the LUKS device is already open
        self.logger.warning("LUKS device 'test_image' is already open, closing it")
        self._run(["cryptsetup", "luksClose", "test_image"])
    except RuntimeError:
        pass
    _allocate_image(self, image_path, padding=32)  # First allocate the image file, adding padding for the LUKS header
    keyfile_path = _get_luks_keyfile(self)
    self.logger.info("Using LUKS keyfile: %s" % c_(keyfile_path, "green"))
    self.logger.info("Creating LUKS image: %s" % c_(image_path, "green"))
    self._run(
        [
            "cryptsetup",
            "luksFormat",
            image_path,
            "--uuid",
            _get_luks_uuid(self),
            "--batch-mode",
            "--key-file",
            keyfile_path,
        ]
    )
    self.logger.info("Opening LUKS image: %s" % c_(image_path, "magenta"))
    self._run(["cryptsetup", "luksOpen", image_path, "test_image", "--key-file", keyfile_path])


def make_test_image(self):
    """Creates a test image from the build dir"""
    build_dir = self._get_build_path("/").resolve()
    self.logger.info("Creating test image from: %s" % c_(build_dir, "blue", bold=True))

    rootfs_type = self["mounts"]["root"]["type"]
    try:
        rootfs_uuid = self["mounts"]["root"]["uuid"]
    except KeyError:
        if rootfs_type != "squashfs":
            raise ValueError("Root filesystem UUID is required for non-squashfs rootfs")

    image_path = self._get_out_path(self["out_file"])

    if self.get("cryptsetup"):  # If there is cryptsetup config, create a LUKS image
        make_test_luks_image(self, image_path)
        image_path = "/dev/mapper/test_image"
    else:
        _allocate_image(self, image_path)

    if rootfs_type == "ext4":
        self._run(["mkfs", "-t", rootfs_type, "-d", build_dir, "-U", rootfs_uuid, "-F", image_path])
    elif rootfs_type == "btrfs":
        self._run(["mkfs", "-t", rootfs_type, "-f", "--rootdir", build_dir, "-U", rootfs_uuid, image_path])
    elif rootfs_type == "xfs":
        self._run(["mkfs", "-t", rootfs_type, "-m", "uuid=%s" % rootfs_uuid, image_path])
        _copy_fs_contents(self, image_path, build_dir)  # XFS doesn't support importing a directory as a filesystem
    elif rootfs_type == "f2fs":
        self._run(["mkfs", "-t", rootfs_type, "-f", "-U", rootfs_uuid, image_path])
        _copy_fs_contents(self, image_path, build_dir)  # F2FS doesn't support importing a directory as a filesystem
    elif rootfs_type == "squashfs":
        # First, make the inner squashfs image
        squashfs_image = self._get_out_path(f"squash/{self['squashfs_image']}")
        if squashfs_image.exists():
            if self.clean:
                self.logger.warning("Removing existing squashfs image file: %s" % c_(squashfs_image, "red"))
                squashfs_image.unlink()
            else:
                raise Exception("File already exists and 'clean' is off: %s" % squashfs_image)
        if not squashfs_image.parent.exists():  # Make sure the parent directory exists
            squashfs_image.parent.mkdir(parents=True)
        self._run(["mksquashfs", build_dir, squashfs_image])
        # Then pack it into an ext4 container
        self._run(["mkfs.ext4", "-d", squashfs_image.parent, "-L", self["livecd_label"], image_path])
    else:
        raise NotImplementedError("Unsupported test rootfs type: %s" % rootfs_type)

    if self.get("cryptsetup"):  # Leave it open in the event of failure, close it before executing tests
        self.logger.info("Closing LUKS image: %s" % c_(image_path, "magenta"))
        self._run(["cryptsetup", "luksClose", "test_image"])
