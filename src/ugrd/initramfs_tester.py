# Tests the initramfs image

from zenlib.logging import loggify
from ugrd.initramfs_generator import InitramfsGenerator


@loggify
class InitramfsTester:
    def __init__(self, initrd_generator, test_kernel, test_dir="/tmp/initramfs_test_rootfs", *args, **kwargs):
        self.initrd_generator = initrd_generator

        self.target_fs = InitramfsGenerator(logger=self.logger, test_kernel=test_kernel, validate=False, build_dir=test_dir, config=None, modules='ugrd.fs.test_image', NO_BASE=True, out_dir=initrd_generator.out_dir, out_file='ugrd-test-rootfs', mounts=initrd_generator['mounts'])

    def test(self):
        print(self.target_fs.__dict__)
        if not self.target_fs['test_kernel']:
            raise ValueError("No 'test_kernel' specfied.")

        if not self.target_fs['test_kernel'].exists():
            raise ValueError("Kernel does not exist: %s" % self.target_fs['test_kernel'])

        self.target_fs.build()
        self.logger.info("Testing initramfs image: %s", self.initrd_generator['_archive_out_path'])
        self.logger.info("Using rootfs: %s", self.target_fs['_archive_out_path'])
        self.logger.info("Using kernel: %s", self.target_fs['test_kernel'])

        qemu_args = {'-m': '512M',
                     '-cpu': 'host',
                     '-kernel': self.target_fs['test_kernel'],
                     '-initrd': self.initrd_generator['_archive_out_path'],
                     '-serial': 'mon:stdio',
                     '-append': 'console=ttyS0,115200 panic=1',
                     '-drive': 'file=%s,format=raw' % self.target_fs['_archive_out_path']}
        qemu_bools = ['-nographic', '-no-reboot', '-enable-kvm']

        arglist = ['qemu-system-x86_64'] + qemu_bools
        for k, v in qemu_args.items():
            arglist.append(k)
            arglist.append(v)
        self.logger.info(self.target_fs._run(arglist))











