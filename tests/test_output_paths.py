from pathlib import Path
from unittest import TestCase, main
from uuid import uuid4

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestOutFile(TestCase):
    def test_absolute_out_file(self):
        out_file = Path(f"/tmp/{uuid4()}.cpio")
        if out_file.exists():
            self.fail(f"File {out_file} already exists")
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", out_file=out_file)
        generator.build()
        self.assertTrue(out_file.exists())
        out_file.unlink()

    def test_named_out_file(self):
        out_file = Path(f"{uuid4()}.cpio")
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", out_file=out_file)
        out_path = generator._get_out_path(out_file)
        if out_path.exists():
            self.fail(f"File {out_path} already exists")
        generator.build()
        self.assertTrue(out_path.exists())

    def test_relative_out_file(self):
        out_file = f"./{uuid4()}.cpio"
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", out_file=out_file)
        out_path = Path(out_file)
        if out_path.exists():
            self.fail(f"File {out_file} already exists")
        generator.build()
        self.assertTrue(out_path.exists())
        out_path.unlink()
        test_image = Path(generator["test_rootfs_name"])
        self.assertTrue(test_image.exists())
        test_image.unlink()

    def test_TMPDIR(self):
        """Tests that the TMPDIR environment variable is respected"""
        from tempfile import TemporaryDirectory
        from os import environ
        try:
            with TemporaryDirectory() as tmpdir:
                environ["TMPDIR"] = tmpdir
                generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
                generator.build()
                self.assertTrue(Path(tmpdir).exists())
                self.assertTrue((Path(tmpdir) / 'initramfs_test' / generator.out_file).exists())
        except Exception as e:
            self.fail(f"Exception: {e}")
        finally:
            environ.pop("TMPDIR")

    def test_implied_relative_output(self):
        """ Tests implied relative output paths. Should resolve out_dir to the current dir. """
        out_file = "implied/relative/path/initrd"
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", out_file=out_file)
        out_path = Path(out_file)
        if out_path.exists():
            self.fail(f"File {out_file} already exists")
        generator.build()
        self.assertTrue(out_path.exists())
        out_path.unlink()
        test_image = out_path.parent / generator["test_rootfs_name"]
        self.assertTrue(test_image.exists())
        test_image.unlink()
        generator["out_dir"].rmdir()



if __name__ == "__main__":
    main()
