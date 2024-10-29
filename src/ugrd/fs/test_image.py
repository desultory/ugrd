__version__ = "0.8.0"

from zenlib.util import contains


@contains("test_flag", "A test flag must be set to create a test image", raise_exception=True)
def init_banner(self):
    """Initialize the test image banner, set a random flag if not set."""
    self["banner"] = f"echo {self['test_flag']}"


def _allocate_image(self, image_path):
    """Allocate the test image size"""
    if image_path.exists():
        if self.clean:
            self.logger.warning("Removing existing filesystem image file: %s" % image_path)
            image_path.unlink()
        else:
            raise Exception("File already exists and 'clean' is off: %s" % image_path)

    with open(image_path, "wb") as f:
        self.logger.info("Allocating test image file: %s" % f.name)
        f.write(b"\0" * self.test_image_size * 2**20)


def make_test_image(self):
    """Creates a test image from the build dir"""
    build_dir = self._get_build_path("/").resolve()
    self.logger.info("Creating test image from: %s" % build_dir)

    rootfs_uuid = self["mounts"]["root"]["uuid"]
    rootfs_type = self["mounts"]["root"]["type"]

    image_path = self._get_out_path(self["out_file"])
    if rootfs_type == "ext4":
        # Create the test image file, flll with 0s
        _allocate_image(self, image_path)
        self._run(["mkfs", "-t", rootfs_type, "-d", build_dir, "-U", rootfs_uuid, "-F", image_path])
    elif rootfs_type == "btrfs":
        if self["clean"] and image_path.exists():
            self.logger.warning("Removing existing test image file: %s" % image_path)
            image_path.unlink()
        self._run(["mkfs", "-t", rootfs_type, "-f", "--rootdir", build_dir, "-U", rootfs_uuid, image_path])
    elif rootfs_type == "xfs":
        _allocate_image(self, image_path)
        self._run(["mkfs", "-t", rootfs_type, "-m", "uuid=%s" % rootfs_uuid, image_path])
        try:  # XFS doesn't support importing a directory as a filesystem, it must be mounted
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as tmp_dir:
                self._run(["mount", image_path, tmp_dir])
                self._run(["cp", "-a", f"{build_dir}/.", tmp_dir])
                self._run(["umount", tmp_dir])
        except RuntimeError as e:
            raise RuntimeError("Could not mount the XFS test image: %s", e)
    else:
        raise NotImplementedError("Unsupported test rootfs type: %s" % rootfs_type)
