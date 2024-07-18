def test_init(self):
    """ Test init function. """
    return "echo DONE"


def make_test_image(self):
    """ Creates a test image from the build dir """

    self.logger.info("Creating test image from: %s" % self.build_dir.resolve())

    # Create the test image file, flll with 0s
    with open(self._archive_out_path, "wb") as f:
        self.logger.info("Creating test image file: %s" % self._archive_out_path)
        f.write(b"\0" * self.test_image_size * 2 ** 20)

    self._run(['mkfs.ext4', '-d', self.build_dir.resolve(), self._archive_out_path])
