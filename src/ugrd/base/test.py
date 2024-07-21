__version__ = "0.2.0"


COPY_CONFIG = ['mounts', 'test_image_size', 'test_flag', 'out_dir', 'clean']


def init_test_vars(self):
    if not self.get("test_kernel"):
        raise ValueError("test_kernel not set")
    if not self['test_kernel'].exists():
        raise FileNotFoundError("Test kernel not found: %s" % self['test_kernel'])


def get_qemu_cmd_args(self):
    """ Gets the qemu command from the configuration """
    qemu_args = {'-m': self['test_memory'],
                 '-cpu': self['test_cpu'],
                 '-kernel': self['test_kernel'],
                 '-initrd': self['_archive_out_path'],
                 '-serial': 'mon:stdio',
                 '-append': self['test_cmdline'],
                 '-drive': 'file=%s,format=raw' % self['_test_rootfs']['_archive_out_path']}

    qemu_bools = [f'-{item}' for item in self['qemu_bool_args']]

    arglist = [f"qemu-system-{self['test_arch']}"] + qemu_bools
    for key, value in qemu_args.items():
        arglist.append(key)
        arglist.append(value)

    self['_qemu_cmd'] = ' '.join(str(arg) for arg in arglist)

    return arglist


def make_test_image(self):
    """ Creates a new initramfs generator to creaate the test image """
    from ugrd.initramfs_generator import InitramfsGenerator

    kwargs = {'logger': self.logger,
              'validate': False,
              'NO_BASE': True,
              'config': None,
              'modules': 'ugrd.fs.test_image',
              'out_file': self['test_rootfs_name'],
              'build_dir': self['test_rootfs_build_dir'],
              **{key: self[key] for key in COPY_CONFIG}}

    target_fs = InitramfsGenerator(**kwargs)
    target_fs.build()
    self['_test_rootfs'] = target_fs


def test_image(self):
    qemu_cmd = get_qemu_cmd_args(self)
    self.logger.info("Testing initramfs image: %s", self['_archive_out_path'])
    self.logger.info("Test kernel: %s", self['test_kernel'])
    self.logger.info("Test rootfs: %s", self['_test_rootfs']['_archive_out_path'])
    self.logger.info("QEMU command: %s", self['_qemu_cmd'])

    try:
        results = self._run(qemu_cmd, timeout=self['test_timeout'])
    except RuntimeError as e:
        self.logger.error("Test failed: %s", e)
        return False

    stdout = results.stdout.decode('utf-8').split('\r\n')
    self.logger.debug("QEMU output: %s", stdout)

    if self['test_flag'] in stdout:
        self.logger.info("Test passed")
    else:
        self.logger.error("Test failed")
        self.logger.error("QEMU stdout:\n%s", stdout)


