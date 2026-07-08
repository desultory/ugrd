from os import fsdecode
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import Mock

from ugrd.base.core import LDConfigError, _get_ldconfig
from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestCore(TestCase):
    def test_conditional_deps(self):
        """Tests that the conditional deps config option works"""
        with TemporaryDirectory() as tmpdir:
            test_dep_inc = Path(tmpdir) / Path("test")
            test_dep_inc.touch()
            test_dep_omit = Path(tmpdir) / Path("test2")
            test_dep_omit.touch()
            generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
            generator["conditional_dependencies"] = {str(test_dep_inc): ["unset", "not_a_var_foo_bar"]}
            generator["conditional_dependencies"] = {str(test_dep_omit): ["contains", "not_a_var_foo_bar"]}
            generator.build()
            self.assertIn(test_dep_inc, generator["dependencies"])
            self.assertNotIn(test_dep_omit, generator["dependencies"])

    def test_get_ldconfig_handles_non_utf8_stdout(self):
        """Ensure ldconfig output with arbitrary path bytes does not crash decoding."""
        cmd = CompletedProcess(["ldconfig", "-p"], 0, b"libgcc_s.so.1 => /usr/lib/libgcc_s-\xe9.so.1\n", b"")
        generator = Mock()
        generator._run.return_value = cmd

        self.assertEqual(_get_ldconfig(generator), fsdecode(cmd.stdout).splitlines())

    def test_get_ldconfig_handles_non_utf8_stderr(self):
        """Ensure ldconfig error output with arbitrary bytes raises LDConfigError."""
        cmd = CompletedProcess(["ldconfig", "-p"], 1, b"", b"fall\xf3 ldconfig\n")
        generator = Mock()
        generator._run.return_value = cmd

        with self.assertRaises(LDConfigError) as error:
            _get_ldconfig(generator)

        self.assertIn(fsdecode(cmd.stderr).strip(), str(error.exception))


if __name__ == "__main__":
    main()
