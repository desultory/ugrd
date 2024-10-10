__author__ = 'desultory'
__version__ = '3.4.3'


from zenlib.util import contains


@contains('check_cpio')
def check_cpio_deps(self) -> None:
    """ Checks that all dependenceis are in the generated CPIO file. """
    for dep in self['dependencies']:
        _check_in_cpio(self, dep)
    return "All dependencies found in CPIO."


@contains('check_cpio')
def check_cpio_funcs(self) -> None:
    """ Checks that all included functions are in the profile included in the generated CPIO file. """
    bash_func_names = [func + '() {' for func in self.included_functions]
    _check_in_cpio(self, 'etc/profile', bash_func_names)
    return "All functions found in CPIO."


@contains('check_in_cpio')
@contains('check_cpio')
def check_in_cpio(self) -> None:
    """ Checks that all required files and lines are in the generated CPIO file. """
    for file, lines in self['check_in_cpio'].items():
        _check_in_cpio(self, file, lines)
    return "All files and lines found in CPIO."


def _check_in_cpio(self, file, lines=[]):
    """ Checks that the file is in the CPIO archive, and it contains the specified lines. """
    cpio = self._cpio_archive
    file = str(file).lstrip('/')  # Normalize as it may be a path
    if file not in cpio.entries:
        self.logger.warning("CPIO entries:\n%s" % '\n'.join(cpio.entries.keys()))
        raise FileNotFoundError("File not found in CPIO: %s" % file)
    else:
        self.logger.debug("File found in CPIO: %s" % file)

    if lines:
        entry_data = cpio.entries[file].data.decode().splitlines()
        for line in lines:
            if line not in entry_data:
                raise FileNotFoundError("Line not found in CPIO: %s" % line)
            else:
                self.logger.debug("Line found in CPIO: %s" % line)


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
    cpio.append_recursive(self._get_build_path('/'), relative=True)

    if self.get('mknod_cpio'):
        for node in self['nodes'].values():
            self.logger.debug("Adding CPIO node: %s" % node)
            cpio.add_chardev(name=node['path'], mode=node['mode'], major=node['major'], minor=node['minor'])

    out_cpio = self['_archive_out_path']
    if not out_cpio.parent.exists():
        self._mkdir(out_cpio.parent, resolve_build=False)

    if out_cpio.exists():
        if self['cpio_rotate']:
            self._rotate_old(out_cpio)
        elif self['clean']:
            self.logger.warning("Removing existing file: %s" % out_cpio)
            out_cpio.unlink()
        else:
            raise FileExistsError("File already exists, and cleaning/rotation are disabled: %s" % out_cpio)

    cpio.write_cpio_file(out_cpio, compression=self['cpio_compression'], _log_bump=-10, _log_init=False)
