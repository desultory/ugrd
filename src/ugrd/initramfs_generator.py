from importlib.metadata import version
from textwrap import dedent
from typing import Any

from zenlib.logging import LoggerMixIn
from zenlib.util import colorize as c_
from zenlib.util import parse_toml, pretty_print

from ugrd import InitramfsConfig

from .exceptions import ValidationError
from .generator_helpers import GeneratorHelpers


class InitramfsGenerator(GeneratorHelpers, LoggerMixIn):
    def __init__(self, config="/etc/ugrd/config.toml", *args, **kwargs) -> None:
        self.init_logger(args, kwargs)
        self.config_dict = InitramfsConfig(NO_BASE=kwargs.pop("NO_BASE", False), logger=self.logger)

        # Used for functions that are added to the shell profile
        # The key name is the function name, the value is the content
        self.included_functions: dict[str, str | list[str]] = {}

        # Used for functions that are run as part of the build process
        self.build_tasks = ["build_enum", "build_pre", "build_tasks", "build_late", "build_deploy", "build_final"]

        # init_pre and init_final are run as part of generate_initramfs_main
        self.init_types = ["init_debug", "init_main", "init_mount"]

        # Passed kwargs must be imported early, so they will be processed against the base configuration
        self.config_dict.import_args(kwargs)

        # don't attempt to load config if not specified
        if not config:
            self.logger.info("No config file specified, using the base config.")
            return

        try:
            self.load_config(config)  # The user config is loaded over the base config, clobbering kwargs
            self.config_dict.import_args(
                kwargs, quiet=True, late=True
            )  # Re-import kwargs (cmdline params) to apply them over the config
        except FileNotFoundError:
            self.logger.critical(f"[{c_(config, 'red')}] Config file not found, using the base config.")

    def load_config(self, config_filename) -> None:
        """
        Loads the config from the specified toml file.
        Populates self.config_dict with the config.
        Ensures that the required parameters are present.
        """
        self.logger.info(f"Loading config file: {c_(config_filename, 'blue', bold=True, bright=True)}")
        raw_config = parse_toml(config_filename)

        # Process all config into the config dict, which will handle processing/validation
        for config, value in raw_config.items():
            self.logger.debug(
                f"[{c_(config_filename, 'blue')}] ({c_(config, bold=True)}) Processing config value: {c_(value, 'green')}"
            )
            self[config] = value

        self.logger.debug(f"Loaded config:\n{self.config_dict}")

    #  If the initramfs generator is used as a dictionary, it will use the config_dict.
    def __setitem__(self, key, value) -> None:
        self.config_dict[key] = value

    def __getitem__(self, item) -> Any:
        return self.config_dict[item]

    def __contains__(self, item) -> bool:
        return item in self.config_dict

    def get(self, item, default=None) -> Any:
        return self.config_dict.get(item, default)

    def __getattr__(self, item) -> Any:
        """Allows access to the config dict via the InitramfsGenerator object."""
        if item not in self.__dict__ and item != "config_dict":
            return self[item]
        return object.__getattribute__(self, item)

    def build(self) -> None:
        """Builds the initramfs image."""
        self._log_run(f"Running ugrd v{version('ugrd')}")
        self.run_build()
        self.config_dict.validate()  # Validate the config after the build tasks have been run

        if self.validate and not self.validated:
            raise ValidationError(
                f"Failed to validate config. Unprocessed values: {', '.join(list(self['_processing'].keys()))}"
            )

        self.generate_init()
        self.pack_build()
        self.run_checks()
        self.run_tests()

    def run_func(self, function, force_include=False, force_exclude=False) -> list[str] | None:
        """
        Runs an imported function.
        The function should return str | list[str] | none

        Normalizes output to list[str] and removes any empty lines or indentation

        If the function name is already included or conflicts with a binary name, raises a ValueError

        If force_include is set, forces the function to be included in the shell profile.
        If force_exclude is set, does not include the output of the function in the shell profile and returns output early
        """
        self.logger.log(self["_build_log_level"], f"Running function: {c_(function.__name__, 'blue', bold=True)}")
        if function_output := function(self):
            if force_exclude:
                # Log the contents and return early
                self.logger.log(5, f"[{c_(function.__name__, 'yellow')}] Excluded function output:\n{function_output}")
                return function_output if isinstance(function_output, list) else [function_output]

            # Check after running for functions which will not be included in the init scripts/profile
            if function.__name__ in self.included_functions:
                raise ValueError(f"Function already included in the shell profile: {c_(function.__name__, 'red')}")

            if function.__name__ in self["binaries"]:
                raise ValueError(f"Function name collides with defined binary: {c_(function.__name__, 'red')}")

            # If the output is only a string, convert it to a list of strings
            if isinstance(function_output, str):
                function_output = [
                    line for line in dedent(function_output).split("\n") if line and line != "\n" and not line.isspace()
                ]

            # If the output is a single line, and force_include is not set, return the contents (not the function name)
            if len(function_output) == 1 and not force_include:
                self.logger.log(
                    5, f"[{c_(function.__name__, 'blue')}] Function returned single line: {function_output[0]}"
                )
                return function_output

            # Otherwise add it to the included functions and return the function name
            self.logger.debug(
                f"[{c_(function.__name__, 'blue')}] Function returned output:\n{pretty_print(function_output)}"
            )
            self.included_functions[function.__name__] = function_output
            self.logger.debug(f"Created function alias: {c_(function.__name__, 'blue')}")
            return [function.__name__]
        elif force_include:
            raise ValueError(f"Force included function returned no output:{c_(function.__name_, 'red')}")
        else:
            self.logger.debug(f"Function returned no output: {c_(function.__name__, 'yellow')}")
            return None

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
                    f"[{c_(hook, bright=True)}] Skipping masked function: {c_(function.__name__, 'yellow', bold=True)}"
                )
                continue

            if function_output := self.run_func(function, *args, **kwargs):
                out += function_output
        return out

    def generate_profile(self) -> list[str]:
        """Generates the shell profile file based on self.included_functions.

        !!! MUST BE RUN AFTER ALL HOOKS ARE RUN !!!
        """
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
            for line in func_content:
                out.append(f"    {line}")
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

        # Run all included functions, so they get included when the profile is generated
        # Run before any other hooks to ensure there are no name conflicts later
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
        """Runs all build tasks based on all build tasks
        Enable force exclude so the output is not used to generate profile functions
        """
        self._log_run("Running build tasks")
        for task in self.build_tasks:
            self.logger.debug("Running build task: %s" % task)
            self.run_hook(task, force_exclude=True)

    def pack_build(self) -> None:
        """Packs the initramfs based on self['imports']['pack']
        Enable force exclude so the output is not used to generate profile function.
        """
        self._log_run("Packing build")
        if self["imports"].get("pack"):
            self.run_hook("pack", force_exclude=True)
        else:
            self.logger.warning(
                "No pack functions specified, the final build is present in: %s"
                % c_(self.build_dir, "green", bold=True, bright=True)
            )

    def run_checks(self) -> None:
        """Runs checks if defined in self['imports']['checks'].
        Enable force exclude so the output is not used to generate profile function.
        """
        self._log_run("Running checks")
        try:
            if check_output := self.run_hook("checks", force_exclude=True):
                for check in check_output:
                    self.logger.debug(check)
            else:
                self.logger.warning("No checks executed.")
        except (FileNotFoundError, ValueError) as e:
            raise ValidationError(f"Error running checks: {e}") from e

    def run_tests(self) -> None:
        """Runs tests if defined in self['imports']['tests'].
        Enable force exclude so any output is not included to generate profile functions.
        """
        if test_output := self.run_hook("tests", force_exclude=True):
            self._log_run("Running tests")
            self.logger.info("Completed tests:\n%s", test_output)
        else:
            self.logger.debug("No tests executed.")

    def run_init_hook(self, level: str) -> list[str]:
        """Runs the specified init hook, returning the output."""
        if runlevel := self.run_hook(level):
            out = ["\n# Begin %s" % level]
            out += runlevel
            return out
        else:
            self.logger.debug("No output for init level: %s" % level)
            return []

    def _log_run(self, logline) -> None:
        self.logger.info(f"-- | {c_(logline, 'blue', bold=True)}")

    def __str__(self) -> str:
        return str(self.config_dict)
