"""
Similar to lddtree
"""


from zen_custom import class_logger, NoDupFlatList


@class_logger
class LibrarySniffer:
    """
    Designed to take binary files and find out what libraries/dependencies are required by the program
    First sees what the environment is using
    """

    parameters = {'ldso_file': '/etc/ld.so.conf'}

    def __init__(self, *args, **kwargs):
        for parameter, default in self.parameters.items():
            val = kwargs.get(parameter, default)
            if not isinstance(val, type(default)):
                raise ValueError("Computed value has an invalid type: %s\nExpected: %s, Detected: %s" % (val, type(default), type(val)))
            setattr(self, parameter, kwargs.get(parameter, default))

        self.library_paths = NoDupFlatList()

        self.parse_ldso()

    def parse_ldso(self, config_file=None):
        """
        Attempts to parse the system /etc/ld.so.conf
        """
        if not config_file:
            config_file = self.ldso_file
        if not config_file.startswith('/'):
            config_file = f"/etc/{config_file}"
            self.logger.debug("Relative path detected")
        if '*' in config_file:
            from glob import glob
            self.logger.info("Glob detected, evaluating and recursing: %s" % config_file)
            for file in glob(config_file):
                return self.parse_ldso(config_file=file)

        self.logger.info("Attempting to parse ld.so file: %s" % config_file)
        with open(config_file, 'r') as ldso:
            from os.path import isdir
            for line in ldso:
                line = line.rstrip()  # remove newline
                if line.startswith("#"):
                    self.logger.debug("Ignoring ld.so comment: %s" % line)
                    continue
                elif line.startswith("include "):
                    include = line.removeprefix("include ")
                    self.logger.info("ld.so include detected, loading: %s" % include)
                    self.parse_ldso(config_file=include)
                elif isdir(line):
                    self.logger.info("Detected ldso config path: %s" % line)
                    self.library_paths.append(line)
                else:
                    self.logger.error("Unable to process '%s' config line: %s" % (ldso.name, line))

