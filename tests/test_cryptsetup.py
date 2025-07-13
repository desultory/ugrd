from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestCryptsetup(TestCase):
    def setUp(self):
        """Create the test keyfile"""
        from pathlib import Path
        from uuid import uuid4

        keyfile = Path("/tmp/ugrd_test_key")
        if keyfile.exists():
            raise FileExistsError("Test Keyfile already exists!: %s" % keyfile)

        with open("/tmp/ugrd_test_key", "wb") as f:
            f.write(uuid4().bytes)

    def tearDown(self):
        """Remove the test keyfile"""
        from pathlib import Path

        keyfile = Path("/tmp/ugrd_test_key")
        if keyfile.exists():
            keyfile.unlink()

    def test_cryptsetup_included_key(self):
        """Tests LUKS based roots using a keyfile included in the initramfs"""
        generator = InitramfsGenerator(logger=self.logger, config="tests/cryptsetup_included_key.toml")
        generator.build()


if __name__ == "__main__":
    main()
