__version__ = "0.7.0"

from zenlib.util import unset


COPY_CONFIG = [
    'mounts', 'out_dir', 'tmpdir', 'clean',
    'test_image_size', 'test_flag'
]


@unset('test_kernel')
def find_kernel_path(self):
    from pathlib import Path
    self.logger.info("Trying to find the kernel path for: %s", self['kernel_version'])
    kernel_path = Path(self['_kmod_dir']) / 'vmlinuz'  # try this first
    if not (self['_kmod_dir'] / 'vmlinuz').exists():
        for search_dir in ['/boot', '/efi']:
            for prefix in ['vmlinuz', 'kernel', 'linux', 'bzImage']:
                kernel_path = Path(search_dir) / f'{prefix}-{self["kernel_version"]}'
                if kernel_path.exists():
                    break
            if kernel_path.exists():
                break
        else:
            raise FileNotFoundError("Kernel not found: %s" % self['kernel_version'])

    self.logger.info("Found kernel at: %s", kernel_path)
    self['test_kernel'] = kernel_path


def init_test_vars(self):
    from uuid import uuid4
    find_kernel_path(self)
    if not self['test_flag']:
        self['test_flag'] = uuid4()


def _get_qemu_cmd_args(self, test_image):
    """ Gets the qemu command from the configuration """
    test_initrd = self._archive_out_path
    test_rootfs = test_image['_archive_out_path']
    qemu_args = {'-m': self['test_memory'],
                 '-cpu': self['test_cpu'],
                 '-kernel': self['test_kernel'],
                 '-initrd': test_initrd,
                 '-serial': 'mon:stdio',
                 '-append': self['test_cmdline'],
                 '-drive': 'file=%s,format=raw' % test_rootfs}

    qemu_bools = [f'-{item}' for item in self['qemu_bool_args']]

    arglist = [f"qemu-system-{self['test_arch']}"] + qemu_bools
    for key, value in qemu_args.items():
        arglist.append(key)
        arglist.append(value)

    return arglist


def make_test_image(self):
    """ Creates a new initramfs generator to create the test image """
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
    try:
        target_fs.build()
    except (FileNotFoundError, RuntimeError) as e:
        self.logger.error("Test image configuration:\n%s", target_fs)
        raise RuntimeError("Failed to build test rootfs: %s" % e)

    return target_fs


def test_image(self):
    image = make_test_image(self)
    qemu_cmd = _get_qemu_cmd_args(self, image)

    self.logger.info("Testing initramfs image: %s", self['_archive_out_path'])
    self.logger.debug("Test config:\n%s", image)
    self.logger.info("Test kernel: %s", self['test_kernel'])
    self.logger.info("Test rootfs: %s", image['_archive_out_path'])
    self.logger.info("Test flag: %s", self['test_flag'])
    self.logger.info("QEMU command: %s", ' '.join([str(arg) for arg in qemu_cmd]))

    try:
        results = self._run(qemu_cmd, timeout=self['test_timeout'])
    except RuntimeError as e:
        raise RuntimeError("QEMU test failed: %s" % e)

    stdout = results.stdout.decode('utf-8').split('\r\n')
    self.logger.debug("QEMU output: %s", stdout)

    # Get the time of the kernel panic
    for line in stdout:
        if line.endswith('exitcode=0x00000000'):
            panic_time = line.split(']')[0][1:].strip()
            self.logger.info("Test took: %s", panic_time)
            break
    else:
        self.logger.warning("Unable to determine test duration from panic message.")

    if self['test_flag'] in stdout:
        self.logger.info("Test passed")
    else:
        self.logger.error("Test failed")
        self.logger.error("QEMU stdout:\n%s", stdout)
        raise RuntimeError("Test failed")
