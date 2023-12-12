__author__ = 'desultory'
__version__ = '2.1.1'


from pycpio import PyCPIO


def make_cpio(self) -> None:
    """
    Creates a CPIO archive from the build directory and writes it to the output directory.
    Raises FileNotFoundError if the output directory does not exist.
    """
    cpio = PyCPIO(logger=self.logger, _log_bump=5)
    cpio.append_recursive(self.build_dir, relative=True)

    if self.config_dict['mknod_cpio']:
        for node in self.config_dict['nodes'].values():
            self.logger.debug("Adding CPIO node: %s" % node)
            cpio.add_chardev(name=node['path'], mode=node['mode'], major=node['major'], minor=node['minor'])

    out_cpio = self.out_dir / self.config_dict['out_file']

    if not out_cpio.parent.exists():
        raise FileNotFoundError("Output directory does not exist: %s" % out_cpio.parent)

    if out_cpio.exists():
        self._rotate_old(out_cpio)

    cpio.write_cpio_file(out_cpio)
