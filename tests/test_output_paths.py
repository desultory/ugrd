from pathlib import Path
from shutil import rmtree
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
        from os import environ
        from tempfile import TemporaryDirectory

        try:
            with TemporaryDirectory() as tmpdir:
                environ["TMPDIR"] = tmpdir
                generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
                generator.build()
                self.assertTrue(Path(tmpdir).exists())
                self.assertTrue((Path(tmpdir) / "initramfs_test" / generator.out_file).exists())
        except Exception as e:
            self.fail(f"Exception: {e}")
        finally:
            environ.pop("TMPDIR")

    def test_implied_relative_output(self):
        """Tests implied relative output paths. Should resolve out_dir to the current dir."""
        out_base_dir = str(uuid4())
        out_file = f"{out_base_dir}/implied/relative/path/initrd"
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
        rmtree(out_base_dir)

    def test_absolute_build_dir(self):
        """Tests that an absolute build directory path is handled correctly."""
        build_dir = Path(f"/tmp/{uuid4()}/{uuid4()}")
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", build_dir=build_dir)
        expected_path = build_dir / "test_file.txt"
        self.assertEqual(expected_path, generator._get_build_path("test_file.txt"))

    def test_relative_build_dir(self):
        """Tests that a relative build directory path is handled correctly."""
        build_dir = Path(f"{uuid4()}")
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", build_dir=build_dir)
        expected_path = generator.tmpdir / build_dir / "test_file.txt"
        self.assertEqual(expected_path, generator._get_build_path("test_file.txt"))

    def test_absolute_build_dir_write(self):
        """Tests writing to an absolute build directory."""
        build_dir = Path(f"/tmp/{uuid4()}/{uuid4()}")
        test_text = str(uuid4())
        if build_dir.exists():
            self.fail(f"Build directory {build_dir} already exists")

        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", build_dir=build_dir)
        generator._write("test_file.txt", [test_text])

        self.assertTrue((build_dir / "test_file.txt").exists(), f"[{build_dir}/test_file.txt] File was not created")
        with open(build_dir / "test_file.txt", "r") as f:
            content = f.read()
        self.assertEqual(
            content,
            test_text,
            f"[{build_dir}/test_file.txt] File content does not match expected text: {content} != {test_text}",
        )
        rmtree(build_dir)

    def test_relative_build_dir_write(self):
        """Tests writing to a relative build directory."""
        build_dir = Path(f"{uuid4()}")
        test_text = str(uuid4())

        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml", build_dir=build_dir)
        generator._write("test_file.txt", [test_text])

        expected_path = generator.tmpdir / build_dir / "test_file.txt"
        self.assertTrue(expected_path.exists(), f"[{expected_path}] File was not created")
        with open(expected_path, "r") as f:
            content = f.read()
        self.assertEqual(
            content, test_text, f"[{expected_path}] File content does not match expected text: {content} != {test_text}"
        )
        rmtree(generator.tmpdir / build_dir)


if __name__ == "__main__":
    main()
