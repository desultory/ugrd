from tomllib import load

from zenlib.logging import loggify
from zenlib.util import pretty_print

from ugrd.initramfs_dict import InitramfsConfigDict

from importlib.metadata import version

from .generator_helpers import GeneratorHelpers

__version__ = version(__package__)
__author__ = "desultory"


@loggify
class InitramfsGenerator(GeneratorHelpers):
    def __init__(self, config='/etc/ugrd/config.toml', *args, **kwargs):
        self.config_filename = config
        self.config_dict = InitramfsConfigDict(logger=self.logger)

        # Used for functions that are added to the bash source file
        self.included_functions = {}

        # Used for functions that are run as part of the build process, build_final is run after init generation
        self.build_tasks = ['build_pre', 'build_tasks']

        # init_pre and init_final are run as part of generate_initramfs_main
        self.init_types = ['init_debug', 'init_early', 'init_main', 'init_late', 'init_premount', 'init_mount', 'init_mount_late', 'init_cleanup']

        self.load_config()
        self.config_dict.import_args(kwargs)
        self.config_dict.validate()

    def load_config(self) -> None:
        """
        Loads the config from the specified toml file.
        Populates self.config_dict with the config.
        Ensures that the required parameters are present.
        """
        with open(self.config_filename, 'rb') as config_file:
            self.logger.info("Loading config file: %s" % config_file.name)
            raw_config = load(config_file)

        # Process into the config dict, it should handle parsing
        for config, value in raw_config.items():
            self.logger.debug("Processing config key: %s" % config)
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
        """ Builds the initramfs. """
        self.logger.info("Building initramfs")
        self.build_structure()
        self.generate_init()
        self.run_hook('build_final')
        self.pack_build()

    def build_structure(self) -> None:
        """ builds the initramfs structure. """
        for hook in self.build_tasks:
            self.run_hook(hook)

    def run_func(self, function, force_include=False) -> list[str]:
        """ Runs a function, If force_include is set, forces the function to be included in the bash source file. """
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

            self.logger.debug("[%s] Function returned output: %s" % (function.__name__, pretty_print(function_output)))
            self.included_functions[function.__name__] = function_output
            self.logger.debug("Created function alias: %s" % function.__name__)
            return function.__name__
        else:
            self.logger.debug("[%s] Function returned no output" % function.__name__)

    def run_hook(self, hook: str, *args, **kwargs) -> list[str]:
        """ Runs a hook for imported functions. """
        out = []
        for function in self['imports'].get(hook, []):
            if function_output := self.run_func(function, *args, **kwargs):
                out.append(function_output)
        return out

    def run_init_hook(self, level: str) -> list[str]:
        """ Runs the specified init hook, returning the output. """
        if runlevel := self.run_hook(level):
            out = ['\n\n# Begin %s' % level]
            out += runlevel
            return out
        else:
            self.logger.debug("No output for init level: %s" % level)

    def generate_init_funcs(self) -> None:
        """ Generates the init functions file based on self.included_functions. """
        out = [self['shebang'],
               f"#\n# Generated by UGRD v{__version__}"]

        for func_name, func_content in self.included_functions.items():
            out.append("\n\n" + func_name + "() {")
            if isinstance(func_content, str):
                out.append(f"    {func_content}")
            elif isinstance(func_content, list):
                for line in func_content:
                    out.append(f"    {line}")
            else:
                raise TypeError("Function content is not a string or list: %s" % func_content)
            out.append("}")

        return out

    def generate_init_main(self) -> list[str]:
        """
        Generates the main init file.
        Just runs each hook  in self.init_types and returns the output
        """
        out = []
        for init_type in self.init_types:
            if runlevel := self.run_init_hook(init_type):
                out.extend(runlevel)
        return out

    def generate_init(self) -> None:
        """ Generates the init file. """
        self.logger.info("Running init generator functions")

        init = [self['shebang']]
        init += [f'echo "Starting UGRD v{__version__}"']

        # Run all included functions, so they get included
        self.run_hook('functions', force_include=True)

        init.extend(self.run_init_hook('init_pre'))

        if self['imports'].get('custom_init') and self.get('_custom_init_file'):
            init += ["\n\n# !!custom_init"]
            init_line, custom_init = self['imports']['custom_init'](self)
            if isinstance(init_line, str):
                init.append(init_line)
            else:
                init.extend(init_line)
        else:
            init.extend(self.generate_init_main())

        init.extend(self.run_init_hook('init_final'))
        init += ["\n\n# END INIT"]

        if self.included_functions:
            self._write('/etc/bash.bashrc', self.generate_init_funcs(), 0o755)
            self.logger.info("Included functions: %s" % ', '.join(list(self.included_functions.keys())))
            if self['imports'].get('custom_init'):
                custom_init.insert(2, f"echo 'Starting custom init, UGRD v{__version__}'")

        if self.get('_custom_init_file'):
            self._write(self['_custom_init_file'], custom_init, 0o755)

        self._write('init', init, 0o755)
        self.logger.debug("Final config:\n%s" % pretty_print(self.config_dict))

    def pack_build(self) -> None:
        """ Packs the initramfs based on self['imports']['pack']."""
        if self['imports'].get('pack'):
            self.run_hook('pack')
        else:
            self.logger.warning("No pack functions specified, the final build is present in: %s" % self.build_dir)

