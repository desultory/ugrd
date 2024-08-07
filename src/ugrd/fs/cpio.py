__author__ = 'desultory'
__version__ = '3.0.1'


from pycpio import PyCPIO


def check_cpio(self, cpio: PyCPIO) -> None:
    """ Checks that all dependenceis are in the generated CPIO file. """
    for dep in self['dependencies']:
        if str(dep) not in cpio.entries:
            raise FileNotFoundError("Dependency not found in CPIO: %s" % dep)
        else:
            self.logger.debug("Dependency found in CPIO: %s" % dep)


def get_archive_path(self) -> str:
    """ Determines the filename for the output CPIO archive based on the current configuration. """
    if out_file := self.get('out_file'):
        self.logger.info("Using specified out_file: %s" % out_file)
    else:
        if self.get('kmod_init'):
            out_file = f"ugrd-{self['kernel_version']}.cpio"
        else:
            out_file = "ugrd.cpio"

        if compression_type := self['cpio_compression']:
            if compression_type.lower() != 'false':  # The variable is a string, so we need to check for the string 'false'
                out_file += f".{compression_type}"

    self['_archive_out_path'] = self.out_dir / out_file


def make_cpio(self) -> None:
    """
    Populates the CPIO archive using the build directory,
    writes it to the output file, and rotates the output file if necessary.
    Creates device nodes in the CPIO archive if the mknod_cpio option is set.
    Raises FileNotFoundError if the output directory does not exist.
    """
    cpio = self._cpio_archive
    cpio.append_recursive(self.build_dir, relative=True)
    check_cpio(self, cpio)

    if self.get('mknod_cpio'):
        for node in self['nodes'].values():
            self.logger.debug("Adding CPIO node: %s" % node)
            cpio.add_chardev(name=node['path'], mode=node['mode'], major=node['major'], minor=node['minor'])

    out_cpio = self['_archive_out_path']

    if not out_cpio.parent.exists():
        self._mkdir(out_cpio.parent)

    if out_cpio.exists():
        if self['cpio_rotate']:
            self._rotate_old(out_cpio)
        elif self['clean']:
            self.logger.warning("Removing existing file: %s" % out_cpio)
            out_cpio.unlink()
        else:
            raise FileExistsError("File already exists, and cleaning/rotation are disabled: %s" % out_cpio)

    cpio.write_cpio_file(out_cpio, compression=self['cpio_compression'], _log_bump=-10, _log_init=False)


def _process_out_file(self, out_file):
    """ Processes the out_file configuration option. """
    from pathlib import Path

    if Path(out_file).is_dir():
        self.logger.info("Specified out_file is a directory, setting out_dir: %s" % out_file)
        self['out_dir'] = out_file
        return

    if out_file.startswith('./'):
        self.logger.debug("Relative out_file path detected: %s" % out_file)
        self['out_dir'] = Path('.').resolve()
        self.logger.info("Resolved out_dir to: %s" % self['out_dir'])
        out_file = Path(out_file[2:])
    elif Path(out_file).parent.is_dir() and str(Path(out_file).parent) != '.':
        self['out_dir'] = Path(out_file).parent
        self.logger.info("Resolved out_dir to: %s" % self['out_dir'])
        out_file = Path(out_file).name
    else:
        out_file = Path(out_file)

    dict.__setitem__(self, 'out_file', out_file)
