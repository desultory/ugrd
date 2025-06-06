from importlib.metadata import version
from textwrap import dedent
from tomllib import TOMLDecodeError, load

from zenlib.logging import loggify
from zenlib.util import colorize as c_
from zenlib.util import pretty_print

from ugrd.initramfs_dict import InitramfsConfigDict

from .exceptions import ValidationError
from .generator_helpers import GeneratorHelpers


@loggify
class InitramfsGenerator(GeneratorHelpers):
    def __init__(self, config="/etc/ugrd/config.toml", *args, **kwargs):
        self.config_dict = InitramfsConfigDict(NO_BASE=kwargs.pop("NO_BASE", False), logger=self.logger)

        # Used for functions that are added to the shell profile
        self.included_functions = {}

        # Used for functions that are run as part of the build process
        self.build_tasks = ["build_enum", "build_pre", "build_tasks", "build_late", "build_deploy", "build_final"]

        # init_pre and init_final are run as part of generate_initramfs_main
        self.init_types = ["init_debug", "init_main", "init_mount"]

        # Passed kwargs must be imported early, so they will be processed against the base configuration
        self.config_dict.import_args(kwargs)
        try:  # Attempt to load the config file, if it exists
            self.load_config(config)  # The user config is loaded over the base config, clobbering kwargs
            self.config_dict.import_args(
                kwargs, quiet=True
            )  # Re-import kwargs (cmdline params) to apply them over the config
        except FileNotFoundError:
            if config:  # If a config file was specified, log an error that it's missing
                self.logger.critical("[%s] Config file not found, using the base config." % config)
            else:  # Otherwise, log info that the base config is being used
                self.logger.info("No config file specified, using the base config.")
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

        with open(config_filename, "rb") as config_file:
            self.logger.info("Loading config file: %s" % c_(config_file.name, "blue", bold=True, bright=True))
            raw_config = load(config_file)

        # Process into the config dict, it should handle parsing
        for config, value in raw_config.items():
            self.logger.debug("[%s] (%s) Processing config value: %s" % (config_file.name, config, value))
            try:
                self[config] = value
            except FileNotFoundError as e:
                raise ValueError("[%s] Error loading config parameter '%s': %s" % (config_file.name, config, e))

        self.logger.debug("Loaded config:\n%s" % self.config_dict)

    #  If the initramfs generator is used as a dictionary, it will use the config_dict.
    def __setitem__(self, key, value):
        self.config_dict[key] = value

    def __getitem__(self, item):
        return self.config_dict[item]

    def __contains__(self, item):
        return item in self.config_dict

    def get(self, item, default=None):
        return self.config_dict.get(item, default)

    def __getattr__(self, item):
        """Allows access to the config dict via the InitramfsGenerator object."""
        if item not in self.__dict__ and item != "config_dict":
            return self[item]
        return super().__getattr__(item)

    def build(self) -> None:
        """Builds the initramfs image."""
        self._log_run(f"Running ugrd v{version('ugrd')}")
        self.run_build()
        self.config_dict.validate()  # Validate the config after the build tasks have been run

        if self.validate and not self.validated:
            raise ValidationError(f"Failed to validate config. Unprocessed values: {', '.join(list(self['_processing'].keys()))}")

        self.generate_init()
        self.pack_build()
        self.run_checks()
        self.run_tests()

    def run_func(self, function, force_include=False, force_exclude=False) -> list[str]:
        """
        Runs an imported function.
        If force_include is set, forces the function to be included in the shell profile.
        if force_exclude is set, does not include the output of the function in the shell profile.
        """
        self.logger.log(self["_build_log_level"], "Running function: %s" % c_(function.__name__, "blue", bold=True))

        if function_output := function(self):
            if isinstance(function_output, list) and len(function_output) == 1:
                self.logger.debug(
                    "[%s] Function returned list with one element: %s" % (function.__name__, function_output[0])
                )
                function_output = function_output[0]

            if function.__name__ in self.included_functions:
                raise ValueError("Function has already been included in the shell profile: %s" % function.__name__)

            if function.__name__ in self["binaries"]:
                raise ValueError("Function name collides with defined binary: %s" % (function.__name__))
                return function_output

            if isinstance(function_output, str) and "\n" in function_output:
                function_output = dedent(function_output)
                function_output = [  # If the output string has a newline, split and get rid of empty lines
                    line for line in function_output.split("\n") if line and line != "\n" and not line.isspace()
                ]

            if isinstance(function_output, str) and not force_include:
                self.logger.debug("[%s] Function returned string: %s" % (function.__name__, function_output))
                return function_output

            if not force_exclude:
                self.logger.debug(
                    "[%s] Function returned output: %s" % (function.__name__, pretty_print(function_output))
                )
                self.included_functions[function.__name__] = function_output
                self.logger.debug("Created function alias: %s" % function.__name__)
            elif function_output:
                self.logger.debug("[%s] Function output was not included: %s" % (function.__name__, function_output))
            return function.__name__
        elif force_include:
            raise ValueError("Force included function returned no output: %s" % function.__name__)
        else:
            self.logger.debug("[%s] Function returned no output" % function.__name__)

    def run_hook(self, hook: str, *args, **kwargs) -> list[str]:
        """Runs all functions for the specified hook.
        If the function is masked, it will be skipped.
        If the function is in import_order, handle the ordering
        """
        self.sort_hook_functions(hook)  # This is in generator_helpers.py
        out = []
        for function in self["imports"].get(hook, []):
            if function.__name__ in self["masks"].get(hook, []):
                self.logger.warning(
                    "[%s] Skipping masked function: %s" % (hook, c_(function.__name__, "yellow", bold=True))
                )
                continue

            if function_output := self.run_func(function, *args, **kwargs):
                out.append(function_output)
        return out

    def generate_profile(self) -> list[str]:
        """Generates the shell profile file based on self.included_functions."""
        ver = version(__package__) or 9999  # Version won't be found unless the package is installed
        out = [
            self["shebang"].split(" ")[0],  # Don't add arguments to the shebang (for the profile)
            f"#\n# Generated by UGRD v{ver}\n#",
        ]

        # Add the library paths
        library_paths = ":".join(self["library_paths"])
        self.logger.debug("Library paths: %s" % library_paths)
        out.append(f"export LD_LIBRARY_PATH={library_paths}")

        # Add search paths
        search_paths = ":".join(self["binary_search_paths"])
        self.logger.debug("Search paths: %s" % search_paths)
        out.append(f"export PATH={search_paths}")

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
        """Generates the init file."""
        self._log_run("Generating init functions")
        init = [self["shebang"]]  # Add the shebang to the top of the init file

        # Run all included functions, so they get included
        self.run_hook("functions", force_include=True)

        init.extend(self.run_init_hook("init_pre"))  # Always run init_pre first

        # If custom_init is used, create the init using that
        if self["imports"].get("custom_init"):
            init += ["\n# !!custom_init"]
            init_line, custom_init = self["imports"]["custom_init"](self)
            if isinstance(init_line, str):
                init.append(init_line)
            else:
                init.extend(init_line)
        else:  # Otherwise, use the standard init generator
            custom_init = None
            init.extend(self.generate_init_main())

        init.extend(self.run_init_hook("init_final"))  # Always run init_final last
        init += ["\n\n# END INIT"]

        if self.included_functions:  # There should always be included functions, if the base config is used
            self._write("/etc/profile", self.generate_profile(), 0o755)
            self.logger.info("Included functions: %s" % ", ".join(list(self.included_functions.keys())))

        # Write the custom init file if it exists
        if custom_init:
            self._write(self["_custom_init_file"], custom_init, 0o755)

        self._write("init", init, 0o755)
        self.logger.debug("Final config:\n%s" % self)

    def run_build(self) -> None:
        """Runs all build tasks."""
        self._log_run("Running build tasks")
        for task in self.build_tasks:
            self.logger.debug("Running build task: %s" % task)
            self.run_hook(task, force_exclude=True)

    def pack_build(self) -> None:
        """Packs the initramfs based on self['imports']['pack']."""
        self._log_run("Packing build")
        if self["imports"].get("pack"):
            self.run_hook("pack")
        else:
            self.logger.warning(
                "No pack functions specified, the final build is present in: %s"
                % c_(self.build_dir, "green", bold=True, bright=True)
            )

    def run_init_hook(self, level: str) -> list[str]:
        """Runs the specified init hook, returning the output."""
        if runlevel := self.run_hook(level):
            out = ["\n# Begin %s" % level]
            out += runlevel
            return out
        else:
            self.logger.debug("No output for init level: %s" % level)
            return []

    def run_checks(self) -> None:
        """Runs checks if defined in self['imports']['checks']."""
        self._log_run("Running checks")
        try:
            if check_output := self.run_hook("checks"):
                for check in check_output:
                    self.logger.debug(check)
            else:
                self.logger.warning("No checks executed.")
        except (FileNotFoundError, ValueError) as e:
            raise ValidationError(f"Error running checks: {e}") from e

    def run_tests(self) -> None:
        """Runs tests if defined in self['imports']['tests']."""
        if test_output := self.run_hook("tests"):
            self._log_run("Running tests")
            self.logger.info("Completed tests:\n%s", test_output)
        else:
            self.logger.debug("No tests executed.")

    def _log_run(self, logline) -> None:
        self.logger.info(f"-- | {c_(logline, 'blue', bold=True)}")

    def __str__(self) -> str:
        return str(self.config_dict)
