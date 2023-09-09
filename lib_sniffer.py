"""
Similar to lddtree
"""

__author__ = 'desultory'
__version__ = '0.1.0'


from zen_custom import loggify, NoDupFlatList

from pathlib import Path


@loggify
class LibrarySniffer:
    """
    Designed to take binary files and find out what libraries/dependencies are required by the program
    First sees what the environment is using
    """

    parameters = {'ldso_file': Path('/etc/ld.so.conf')}

    def __init__(self, *args, **kwargs):
        for parameter, default in self.parameters.items():
            val = kwargs.get(parameter, default)
            if not isinstance(val, type(default)):
                raise ValueError("Computed value has an invalid type: %s\nExpected: %s, Detected: %s" % (val, type(default), type(val)))
            setattr(self, parameter, kwargs.get(parameter, default))

        self.library_paths = NoDupFlatList(logger=self.logger, log_bump=10, _log_init=False)

        self.parse_ldso()

    def parse_ldso(self, config_file=None):
        """
        Attempts to parse the system /etc/ld.so.conf
        """
        if not config_file:
            config_file = self.ldso_file

        config_file = config_file if config_file.is_absolute() else "/etc" / config_file

        # Handle globs
        if any(char in '*?[]' for char in str(config_file)):
            self.logger.info("Glob detected, evaluating: %s" % config_file)
            for file_match in config_file.parent.glob(config_file.name):
                self.logger.info("Recursing into glob match: %s" % file_match)
                return self.parse_ldso(config_file=Path(file_match))

        self.logger.info("Attempting to parse ld.so file: %s" % config_file)
        with open(config_file, 'r') as ldso:
            from os.path import isdir  # just used to check if the line in a file is a directory
            for line in ldso:
                line = line.rstrip()  # remove newline
                if line.startswith("#"):
                    self.logger.debug("Ignoring ld.so comment: %s" % line)
                    continue
                elif line.startswith("include "):
                    include = line.removeprefix("include ")
                    self.logger.info("ld.so include detected, loading: %s" % include)
                    self.parse_ldso(config_file=Path(include))
                elif isdir(line):
                    self.logger.info("Detected ldso config path: %s" % line)
                    self.library_paths.append(line)
                else:
                    self.logger.error("Unable to process '%s' config line: %s" % (ldso.name, line))

