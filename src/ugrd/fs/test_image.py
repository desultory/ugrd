def test_init(self):
    """ Test init function. """
    return "echo DONE"


def make_test_image(self):
    """ Creates a test image from the build dir """

    self.logger.info("Creating test image from: %s" % self.build_dir)
