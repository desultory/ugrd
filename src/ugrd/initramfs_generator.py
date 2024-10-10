from tomllib import load, TOMLDecodeError

from zenlib.logging import loggify
from zenlib.util import pretty_print

from ugrd.initramfs_dict import InitramfsConfigDict
from .generator_helpers import GeneratorHelpers


@loggify
class InitramfsGenerator(GeneratorHelpers):
    def __init__(self, config='/etc/ugrd/config.toml', *args, **kwargs):
        self.config_dict = InitramfsConfigDict(NO_BASE=kwargs.pop('NO_BASE', False), logger=self.logger, _log_init=False)

        # Used for functions that are added to the bash source file
        self.included_functions = {}

        # Used for functions that are run as part of the build process
        self.build_tasks = ['build_pre', 'build_tasks', 'build_late', 'build_deploy', 'build_final']

        # init_pre and init_final are run as part of generate_initramfs_main
        self.init_types = ['init_debug', 'init_early', 'init_main', 'init_late', 'init_premount', 'init_mount', 'init_mount_late', 'init_cleanup']

        # Passed kwargs must be imported early, so they will be processed against the base configuration
        self.config_dict.import_args(kwargs)
        try:
            self.load_config(config)  # The user config is loaded over the base config, clobbering kwargs
            self.config_dict.import_args(kwargs)  # Re-import kwargs (cmdline params) to apply them over the config
        except FileNotFoundError:
            self.logger.warning("[%s] Config file not found, using the base config." % config)
        except TOMLDecodeError as e:
            raise ValueError("[%s] Error decoding config file: %s" % (config, e))

    def load_config(self, config_filename) -> None:
        """
        Loads the config from the specified toml file.
        Populates self.config_dict with the config.
        Ensures that the required parameters are present.
        """
        if not config_filename:
            raise FileNotFoundError("Config file not specified.")

        with open(config_filename, 'rb') as config_file:
            self.logger.info("Loading config file: %s" % config_file.name)
            raw_config = load(config_file)

        # Process into the config dict, it should handle parsing
        for config, value in raw_config.items():
            self.logger.debug("[%s] (%s) Processing config value: %s" % (config_file.name, config, value))
            self[config] = value

        self.logger.debug("Loaded config:\n%s" % self.config_dict)

    def __setitem__(self, key, value):
        self.config_dict[key] = value

    def __getitem__(self, item):
        return self.config_dict[item]

    def __contains__(self, item):
        return item in self.config_dict

    def get(self, item, default=None):
        return self.config_dict.get(item, default)

    def __getattr__(self, item):
        """ Allows access to the config dict via the InitramfsGenerator object. """
        if item not in self.__dict__ and item != 'config_dict':
            return self[item]
        return super().__getattr__(item)

    def build(self) -> None:
        """ Builds the initramfs image. """
        from importlib.metadata import version
        self._log_run(f"Running ugrd v{version('ugrd')}")
        self.run_build()
        self.config_dict.validate()  # Validate the config after the build tasks have been run

        self.generate_init()
        self.pack_build()
        self.run_checks()
        self.run_tests()

    def run_func(self, function, force_include=False, force_exclude=False) -> list[str]:
        """
        Runs an imported function.
        If force_include is set, forces the function to be included in the bash source file.
        if force_exclude is set, does not include the output of the function in the bash source file.
        """
        self.logger.log(self['_build_log_level'], "Running function: %s" % function.__name__)

        if function_output := function(self):
            if isinstance(function_output, list) and len(function_output) == 1:
                self.logger.debug("[%s] Function returned list with one element: %s" % (function.__name__, function_output[0]))
                function_output = function_output[0]

            if function.__name__ in self.included_functions:
                raise ValueError("Function '%s' has already been included in the bash source file" % function.__name__)

            if function.__name__ in self['binaries']:
                raise ValueError("Function name collides with defined binary: %s" % (function.__name__))
                return function_output

            if isinstance(function_output, str) and not force_include:
                self.logger.debug("[%s] Function returned string: %s" % (function.__name__, function_output))
                return function_output

            if not force_exclude:
                self.logger.debug("[%s] Function returned output: %s" % (function.__name__, pretty_print(function_output)))
                self.included_functions[function.__name__] = function_output
                self.logger.debug("Created function alias: %s" % function.__name__)
            elif function_output:
                self.logger.debug("[%s] Function output was not included: %s" % (function.__name__, function_output))
            return function.__name__
        else:
            self.logger.debug("[%s] Function returned no output" % function.__name__)

    def run_hook(self, hook: str, *args, **kwargs) -> list[str]:
        """ Runs a hook for imported functions. """
        out = []
        for function in self['imports'].get(hook, []):
            # Check that the function is not masked
            if function.__name__ in self['masks'].get(hook, []):
                self.logger.warning("[%s] Skipping masked function: %s" % (hook, function.__name__))
                continue
            if function_output := self.run_func(function, *args, **kwargs):
                out.append(function_output)
        return out

    def generate_profile(self) -> list[str]:
        """ Generates the bash profile file based on self.included_functions. """
        from importlib.metadata import version
        ver = version(__package__) or 9999   # Version won't be found unless the package is installed
        out = [self['shebang'].split(' ')[0],  # Don't add arguments to the shebang (for the profile)
               f"#\n# Generated by UGRD v{ver}\n#"]

        # Add the library paths
        library_paths = ":".join(self['library_paths'])
        self.logger.debug("Library paths: %s" % library_paths)
        out.append(f"export LD_LIBRARY_PATH={library_paths}")

        for func_name, func_content in self.included_functions.items():
            out.append("\n\n" + func_name + "() {")
            if isinstance(func_content, str):
                out.append(f"    {func_content}")
            elif isinstance(func_content, list):
                for line in func_content:
                    out.append(f"    {line}")
            else:
                raise TypeError("[%s] Function content is not a string or list: %s" % (func_name, func_content))
            out.append("}")

        return out

    def generate_init_main(self) -> list[str]:
        """
        Generates the main init file.
        Just runs each hook in self.init_types and returns the output.
        These hooks include all init levels but init_pre and init_final.
        If a 'custom_init' function is defined, it will be used instead of this function.
        """
        out = []
        for init_type in self.init_types:
            if runlevel := self.run_init_hook(init_type):
                out.extend(runlevel)
        return out

    def generate_init(self) -> None:
        """ Generates the init file. """
        self._log_run("Generating init functions")
        init = [self['shebang']]  # Add the shebang to the top of the init file

        # Run all included functions, so they get included
        self.run_hook('functions', force_include=True)

        init.extend(self.run_init_hook('init_pre'))  # Always run init_pre first

        # If custom_init is used, create the init using that
        if self['imports'].get('custom_init') and self.get('_custom_init_file'):
            init += ["\n# !!custom_init"]
            init_line, custom_init = self['imports']['custom_init'](self)
            if isinstance(init_line, str):
                init.append(init_line)
            else:
                init.extend(init_line)
        else:  # Otherwise, use the standard init generator
            init.extend(self.generate_init_main())

        init.extend(self.run_init_hook('init_final'))  # Always run init_final last
        init += ["\n\n# END INIT"]

        if self.included_functions:  # There should always be included functions, if the base config is used
            self._write('/etc/profile', self.generate_profile(), 0o755)
            self.logger.info("Included functions: %s" % ', '.join(list(self.included_functions.keys())))

        if self.get('_custom_init_file'):  # Write the custom init file if it exists
            self._write(self['_custom_init_file'], custom_init, 0o755)

        self._write('init', init, 0o755)
        self.logger.debug("Final config:\n%s" % self)

    def run_build(self) -> None:
        """ Runs all build tasks. """
        self._log_run("Running build tasks")
        for task in self.build_tasks:
            self.logger.debug("Running build task: %s" % task)
            self.run_hook(task, force_exclude=True)

    def pack_build(self) -> None:
        """ Packs the initramfs based on self['imports']['pack']."""
        self._log_run("Packing build")
        if self['imports'].get('pack'):
            self.run_hook('pack')
        else:
            self.logger.warning("No pack functions specified, the final build is present in: %s" % self.build_dir)

    def run_init_hook(self, level: str) -> list[str]:
        """ Runs the specified init hook, returning the output. """
        if runlevel := self.run_hook(level):
            out = ['\n# Begin %s' % level]
            out += runlevel
            return out
        else:
            self.logger.debug("No output for init level: %s" % level)
            return []

    def run_checks(self) -> None:
        """ Runs checks if defined in self['imports']['checks']. """
        self._log_run("Running checks")
        if check_output := self.run_hook('checks'):
            for check in check_output:
                self.logger.debug(check)
        else:
            self.logger.warning("No checks executed.")

    def run_tests(self) -> None:
        """ Runs tests if defined in self['imports']['tests']. """
        if test_output := self.run_hook('tests'):
            self._log_run("Running tests")
            self.logger.info("Completed tests:\n%s", test_output)
        else:
            self.logger.debug("No tests executed.")

    def _log_run(self, logline) -> None:
        self.logger.info(f"-- | {logline}")

    def __str__(self) -> str:
        return str(self.config_dict)

