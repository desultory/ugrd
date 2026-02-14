from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


def check_devpts(self):
    """Shell script to check if devpts is mounted at /dev/pts."""
    return """
    if [ ! -d /dev/pts ]; then
        rd_fail "devpts check failed, /dev/pts does not exist"
    fi
    if ! grep -q "devpts" /proc/mounts ; then
        rd_fail "devpts check failed, devpts is not mounted at /dev/pts"
    fi
    if [ ! -c /dev/pts/ptmx ]; then
        rd_fail "devpts check failed, /dev/pts/ptmx does not exist or is not a character device"
    fi
    einfo "devpts check passed, devpts is correctly mounted at /dev/pts"
    """


@loggify
class TestMountOptions(TestCase):
    def test_devpts(self):
        """Tests that the 'mount_devpts' option correctly mounts devpts at /dev/pts."""
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
        generator["mount_devpts"] = True
        generator["imports"]["init_main"] += check_devpts
        generator["import_order"]["after"]["mount_fstab"] = "check_devpts"
        generator.build()


if __name__ == "__main__":
    main()
