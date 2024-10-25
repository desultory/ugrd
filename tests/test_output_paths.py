from unittest import TestCase, main
from pathlib import Path
from uuid import uuid4

from ugrd.initramfs_generator import InitramfsGenerator

from zenlib.logging import loggify


@loggify
class TestOutFile(TestCase):
    def test_absolute_out_file(self):
        out_file = Path(f'/tmp/{uuid4()}.cpio')
        if out_file.exists():
            self.fail(f'File {out_file} already exists')
        generator = InitramfsGenerator(logger=self.logger, config='tests/fullauto.toml', out_file=out_file)
        generator.build()
        self.assertTrue(out_file.exists())
        out_file.unlink()

    def test_named_out_file(self):
        out_file = Path(f"{uuid4()}.cpio")
        generator = InitramfsGenerator(logger=self.logger, config='tests/fullauto.toml', out_file=out_file)
        out_path = generator._get_out_path(out_file)
        if out_path.exists():
            self.fail(f'File {out_path} already exists')
        generator.build()
        self.assertTrue(out_path.exists())


    def test_relative_out_file(self):
        out_file = f'./{uuid4()}.cpio'
        generator = InitramfsGenerator(logger=self.logger, config='tests/fullauto.toml', out_file=out_file)
        out_path = Path(out_file)
        if out_path.exists():
            self.fail(f'File {out_file} already exists')
        generator.build()
        self.assertTrue(out_path.exists())
        out_path.unlink()


if __name__ == '__main__':
    main()
