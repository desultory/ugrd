__author__ = 'desultory'
__version__ = '2.4.2'


from pycpio import PyCPIO


def make_cpio(self) -> None:
    """
    Creates a CPIO archive from the build directory and writes it to the output directory.
    Raises FileNotFoundError if the output directory does not exist.
    """
    cpio = PyCPIO(logger=self.logger, _log_bump=5)
    cpio.append_recursive(self.build_dir, relative=True)

    if self.get('mknod_cpio:'):
        for node in self['nodes'].values():
            self.logger.debug("Adding CPIO node: %s" % node)
            cpio.add_chardev(name=node['path'], mode=node['mode'], major=node['major'], minor=node['minor'])

    out_cpio = self.out_dir / self.out_file

    if not out_cpio.parent.exists():
        self._mkdir(out_cpio.parent)

    if out_cpio.exists():
        self._rotate_old(out_cpio)

    cpio.write_cpio_file(out_cpio, _log_bump=-10)


def _process_out_file(self, out_file):
    """
    Processes the out_file configuration option.
    """
    if not out_file:
        raise ValueError("out_file cannot be empty")

    if out_file.startswith('./'):
        from pathlib import Path
        self.logger.debug("Relative out_file path detected: %s" % out_file)
        self['out_dir'] = Path('.').resolve()
        self.logger.info("out_dir resolve to: %s" % self['out_dir'])
        out_file = Path(out_file[2:])

    dict.__setitem__(self, 'out_file', out_file)
