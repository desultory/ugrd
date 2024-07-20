__version__ = "0.3.0"


def init_test_vars(self):
    if not self.get('test_kernel'):
        raise ValueError("No test kernel specified")
    elif not self['test_kernel'].exists():
        raise FileNotFoundError("Test kernel not found: %s" % self['test_kernel'])

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

