# Tests the initramfs image

from zenlib.logging import loggify
from ugrd.initramfs_generator import InitramfsGenerator


@loggify
class InitramfsTester:
    def __init__(self, initrd_generator, test_kernel, test_dir="/tmp/initramfs_test_rootfs", *args, **kwargs):
        self.initrd_generator = initrd_generator

        self.target_fs = InitramfsGenerator(logger=self.logger, test_kernel=test_kernel, validate=False, build_dir=test_dir, config=None, modules='ugrd.fs.test_image', NO_BASE=True, out_dir=initrd_generator.out_dir, out_file='ugrd-test-rootfs', mounts=initrd_generator['mounts'])

    def test(self):
        self.target_fs.build()
        self.logger.info("Testing initramfs image: %s", self.initrd_generator['_archive_out_path'])
        self.logger.info("Using rootfs: %s", self.target_fs['_archive_out_path'])
        self.logger.info("Using kernel: %s", self.target_fs['test_kernel'])

        qemu_args = {'-m': self.target_fs['test_memory'],
                     '-cpu': 'host',
                     '-kernel': self.target_fs['test_kernel'],
                     '-initrd': self.initrd_generator['_archive_out_path'],
                     '-serial': 'mon:stdio',
                     '-append': self.target_fs['test_cmdline'],
                     '-drive': 'file=%s,format=raw' % self.target_fs['_archive_out_path']}
        qemu_bools = ['-nographic', '-no-reboot', '-enable-kvm']

        arglist = [f"qemu-system-{self.target_fs['qemu_arch']}"] + qemu_bools
        for k, v in qemu_args.items():
            arglist.append(k)
            arglist.append(v)
        results = self.target_fs._run(arglist)
        stdout = results.stdout.decode('utf-8').split('\r\n')
        self.logger.debug("QEMU stdout: %s", stdout)
        if self.target_fs['test_flag'] in stdout:
            self.logger.info("Test passed.")
        else:
            self.logger.error("Test failed.")
            self.logger.error("QEMU stdout: %s", stdout)











