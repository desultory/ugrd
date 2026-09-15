from pathlib import Path as FilesystemPath
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import Mock, patch

from ugrd.base.core import autodetect_musl


class DummyGenerator(dict):
    def __init__(self, library_paths):
        super().__init__(library_paths=library_paths, musl_libc=True)
        self.logger = Mock()

    def __setitem__(self, key, value):
        if key == "library_paths" and isinstance(value, str):
            if value not in self[key]:
                self[key].append(value)
            return
        super().__setitem__(key, value)


class TestMusl(TestCase):
    @patch("ugrd.base.core.uname")
    @patch("ugrd.base.core.Path")
    def test_musl_path_file_is_included(self, path_type, uname):
        with TemporaryDirectory() as directory:
            path_file = FilesystemPath(directory, "ld-musl-test.path")
            path_file.touch()
            path_type.return_value = path_file
            uname.return_value = SimpleNamespace(machine="test")
            generator = DummyGenerator(["/custom/lib"])

            autodetect_musl(generator)

            self.assertEqual(generator["dependencies"], path_file)
            self.assertEqual(generator["library_paths"], ["/custom/lib"])

    @patch("ugrd.base.core.uname")
    @patch("ugrd.base.core.Path")
    def test_missing_musl_path_file_uses_fallback_paths(self, path_type, uname):
        with TemporaryDirectory() as directory:
            path_type.return_value = FilesystemPath(directory, "ld-musl-test.path")
            uname.return_value = SimpleNamespace(machine="test")
            generator = DummyGenerator(["/custom/lib", "/lib"])

            autodetect_musl(generator)

            self.assertEqual(
                generator["library_paths"], ["/custom/lib", "/lib", "/usr/lib"]
            )
            generator.logger.warning.assert_called_once()


if __name__ == "__main__":
    main()
