from os import fsdecode
from subprocess import CompletedProcess
from unittest import TestCase, main
from unittest.mock import Mock

from ugrd.base.core import LDConfigError, _get_ldconfig


class TestCore(TestCase):
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
