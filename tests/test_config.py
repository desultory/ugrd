from unittest import TestCase, main

from ugrd.exceptions import ValidationError
from ugrd.initramfs_generator import InitramfsConfig
from zenlib.logging import loggify


@loggify
class TestConfig(TestCase):
    def test_custom_parameter(self):
        """Tests that a custom parameter type can be defined and used"""
        config = InitramfsConfig(logger=self.logger, NO_BASE=True)
        config["custom_parameters"]["foo"] = bool
        config["foo"] = True

        self.assertEqual(config.get("foo"), True)

    def test_custom_parameter_from_dict(self):
        """Tests that a custom parameter can be defined as a dict of strings and used"""
        config = InitramfsConfig(logger=self.logger, NO_BASE=True)
        config["custom_parameters"] = {"foo": "bool"}
        config["foo"] = True

        self.assertEqual(config.get("foo"), True)

    def test_late_arg(self):
        """Tests that a late arg is not processed until the late stage"""
        config = InitramfsConfig(logger=self.logger, NO_BASE=True)
        config["custom_parameters"] = {"foo": "bool"}
        config["_late_args"] = "foo"
        config["foo"] = True

        # hol up
        self.assertEqual(config.get("foo"), False)

        # ready up
        config["stage"] = "late"
        self.assertEqual(config.get("foo"), True)

    def test_validation(self):
        """Tests that unprocessed config raises a ValidationError"""
        config = InitramfsConfig(logger=self.logger, NO_BASE=True)
        config["foo"] = True
        with self.assertRaises(ValidationError):
            config["stage"] = "final"


if __name__ == "__main__":
    main()
