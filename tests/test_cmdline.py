from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


def test_bool_functionality(self) -> str:
    return """
    if check_var test_bool; then
        echo $(readvar test_flag)
    fi
    rd_fail "Failed to read test arg from the cmdline"
    """

def test_string_functionality(self) -> str:
    return """
    if [ "$(readvar test_string)" = "foo=bar" ]; then
        echo $(readvar test_flag)
    fi
    rd_fail "Failed to read test arg from the cmdline"
    """

def export_test_flag(self) -> None:
    self["exports"]["test_flag"] = self["test_flag"]

@loggify
class TestCore(TestCase):
    def test_cmdline_bool(self):
        """ Tests that cmdline bool processing works """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
        generator["imports"]["build_pre"] += export_test_flag
        generator["imports"]["init_main"] += test_bool_functionality
        generator["import_order"]["after"]["export_test_flag"] = "init_test_vars"
        generator["cmdline_bools"] = "test_bool"
        generator["test_cmdline"] += " test_bool"
        generator.build()

    def test_cmdline_str(self):
        """ Tests that cmdline string processing works """
        generator = InitramfsGenerator(logger=self.logger, config="tests/fullauto.toml")
        generator.logger.setLevel(5)
        generator["imports"]["build_pre"] += export_test_flag
        generator["imports"]["init_main"] += test_string_functionality
        generator["import_order"]["after"]["export_test_flag"] = "init_test_vars"
        generator["cmdline_strings"] = "test_string"
        generator["test_cmdline"] += " test_string=foo=bar"
        generator.build()

if __name__ == "__main__":
    main()
