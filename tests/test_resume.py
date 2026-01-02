from unittest import TestCase, main

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import loggify


@loggify
class TestResume(TestCase):
    def test_resume(self):
        generator = InitramfsGenerator(logger=self.logger, config="tests/resume.toml")
        generator.build()


if __name__ == "__main__":
    main()
