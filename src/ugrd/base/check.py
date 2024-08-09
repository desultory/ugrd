__version__ = '0.1.2'

from zenlib.util import contains


def run_checks(self):
    """Run all checks."""
    self.logger.info('Running checks')
    check_included_funcs(self)
    check_in_file(self)


@contains('check_included_funcs', 'Skipping included funcs check', log_level=30)
def check_included_funcs(self):
    bash_func_names = [func + '() {\n' for func in self.included_functions]
    _check_in_file(self, '/etc/profile', bash_func_names)


def check_in_file(self):
    """ Runs all 'check_in_file' checks. """
    for file, lines in self['check_in_file'].items():
        _check_in_file(self, file, lines)


def _check_in_file(self, file, lines):
    """ Checks that all lines are in the file. """
    file = self._get_build_path(file)
    if not file.exists():
        raise ValueError("File '%s' does not exist" % file)

    with open(file, 'r') as f:
        file_lines = f.readlines()

    for check_line in lines:
        if check_line not in file_lines:
            raise ValueError("Failed to find line '%s' in file '%s'" % (check_line, file))

