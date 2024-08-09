__version__ = "0.4.1"

from zenlib.util import contains


@contains('test_flag', 'A test flag must be set to create a test image', raise_exception=True)
def init_banner(self):
    """ Initialize the test image banner, set a random flag if not set. """
    self['banner'] = f"echo {self['test_flag']}"


def make_test_image(self):
    """ Creates a test image from the build dir """
    self.logger.info("Creating test image from: %s" % self.build_dir.resolve())

    # Create the test image file, flll with 0s
    with open(self._archive_out_path, "wb") as f:
        self.logger.info("Creating test image file: %s" % self._archive_out_path)
        f.write(b"\0" * self.test_image_size * 2 ** 20)

    rootfs_uuid = self['mounts']['root']['uuid']
    rootfs_type = self['mounts']['root']['type']

    if rootfs_type == 'ext4':
        self._run(['mkfs', '-t', rootfs_type, '-d', self.build_dir.resolve(), '-U', rootfs_uuid, '-F', self._archive_out_path])
    elif rootfs_type == 'btrfs':
        self._run(['mkfs', '-t', rootfs_type, '--rootdir', self.build_dir.resolve(), '-U', rootfs_uuid, self._archive_out_path])
    else:
        raise Exception("Unsupported test rootfs type: %s" % rootfs_type)

