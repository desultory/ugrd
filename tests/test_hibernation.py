from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestHibernation(TestCase):
    def test_swap_partition(self):
        """Test swap partition hibernation functionality."""
        #generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", test_swap_partition=True, test_kernel="/boot/vmlinuz-6.12.63-gentoo-dist", kernel_version="6.12.63-gentoo-dist")
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", test_swap_partition=True)
        generator.build()

    def test_resume_no_hibernate(self):
        """ Test with the resume module but without hibernating """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", modules="ugrd.fs.resume")
        generator.build()

if __name__ == "__main__":
    main()
