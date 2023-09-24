
__author__ = "desultory"
__version__ = "0.6.0"

from subprocess import run
from tomllib import load
from pathlib import Path

#  from lib_sniffer import LibrarySniffer
from zen_custom import loggify, handle_plural, NoDupFlatList


def calculate_dependencies(binary):
    binary_path = run(['which', binary], capture_output=True).stdout.decode('utf-8').strip()
    dependencies = run(['lddtree', '-l', binary_path], capture_output=True)
    if dependencies.returncode != 0:
        raise OSError(dependencies.stderr.decode('utf-8'))
    return dependencies.stdout.decode('utf-8').splitlines()


@loggify
class InitramfsConfigDict(dict):
    """
    Dict for containing config for the InitramfsGenerator

    IMPORTANT:
        This dict does not act like a normal dict, setitem is designed to append when the overrides are used
        Default parameters are defined in builtin_parameters
    """
    __version__ = "0.5.5"

    builtin_parameters = {'binaries': NoDupFlatList,
                          'dependencies': NoDupFlatList,
                          'paths': NoDupFlatList,
                          'modules': NoDupFlatList,
                          'mounts': dict,
                          'imports': dict,
                          'custom_parameters': dict,
                          'custom_processing': dict}

    def __init__(self, *args, **kwargs):
        # Define the default parameters
        for parameter, default_type in self.builtin_parameters.items():
            if default_type == NoDupFlatList:
                super().__setitem__(parameter, default_type(no_warn=True, log_bump=10, logger=self.logger, _log_init=False))
            else:
                super().__setitem__(parameter, default_type())

    def __setitem__(self, key, value):
        # If the type is registered, use the appropriate update function
        if expected_type := self.builtin_parameters.get(key, self['custom_parameters'].get(key)):
            if hasattr(self, f"_process_{key}"):
                self.logger.debug("Using builtin setitem for: %s" % key)
                getattr(self, f"_process_{key}")(value)
            elif func := self['custom_processing'].get(f"_process_{key}"):
                self.logger.info("Using custom setitem for: %s" % key)
                func(self, value)
            elif func := self['custom_processing'].get(f"_process_{key}_multi"):
                self.logger.info("Using custom plural setitem for: %s" % key)
                handle_plural(func)(self, value)
            elif expected_type in (list, NoDupFlatList):
                self.logger.debug("Using list setitem for: %s" % key)
                self[key].append(value)
            elif expected_type == dict:
                self.logger.debug("Using dict setitem for: %s" % key)
                if key not in self:
                    self.logger.info("Setting dict '%s' to: %s" % (key, value))
                    super().__setitem__(key, value)
                else:
                    self.logger.info("Updating dict '%s' with: %s" % (key, value))
                    self[key].update(value)
            else:
                super().__setitem__(key, expected_type(value))
        else:  # Otherwise set it like a normal dict item
            self.logger.error("Detected undefined parameter type '%s' with value: %s" % (key, value))
            super().__setitem__(key, value)

    @handle_plural
    def update_dict(self, name: str, key: str, value: dict):
        """
        Updates a dict in the internal dictionary
        """
        if key not in self[name]:
            self[name][key] = value
            self.logger.info("Set %s[%s] to: %s" % (name, key, value))
        else:
            self[name][key] = value
            self.logger.warning("%s[%s] already set" % (name, key))

    @handle_plural
    def _process_custom_parameters(self, parameter_name, parameter_type):
        """
        Updates the custom_parameters attribute
        """
        self['custom_parameters'][parameter_name] = eval(parameter_type)
        self.logger.info("Registered custom parameter '%s' with type: %s" % (parameter_name, parameter_type))

        if parameter_type == "NoDupFlatList":
            super().__setitem__(parameter_name, NoDupFlatList(no_warn=True, log_bump=10, logger=self.logger, _log_init=False))
        elif parameter_type == "list":
            super().__setitem__(parameter_name, [])
            self[parameter_name] = []

    @handle_plural
    def _process_binaries(self, binary):
        """
        processes passed binary(ies) into the 'binaries' list
        updates the dependencies using the passed binary name
        """
        self.logger.debug("Calculating dependencies for: %s" % binary)
        dependencies = calculate_dependencies(binary)

        self.logger.debug("Calculating library paths for: %s" % dependencies)
        self['dependencies'] += dependencies

        self['binaries'].append(binary)

    @handle_plural
    def _process_imports(self, import_type: str, import_value: dict):
        """
        Processes imports in a module
        """
        self.logger.debug("Processing imports of type '%s'" % import_type)

        from importlib import import_module
        for module_name, function_names in import_value.items():
            self.logger.debug("Importing module: %s" % module_name)
            function_list = [getattr(import_module(f"{module_name}"), function_name) for function_name in function_names]

            if import_type not in self['imports']:
                self['imports'][import_type] = NoDupFlatList(log_bump=10, logger=self.logger, _log_init=False)
            self['imports'][import_type] += function_list
            self.logger.info("Updated import '%s': %s" % (import_type, function_list))

            if import_type == 'config_processing':
                for function in function_list:
                    self['custom_processing'][function.__name__] = function
                    self.logger.info("Registered config processing function: %s" % function.__name__)

    @handle_plural
    def _process_modules(self, module):
        """
        processes a single module into the config
        takes list with decorator
        """
        self.logger.debug("Processing module: %s" % module)

        with open(f"{module.replace('.', '/')}.toml", 'rb') as module_file:
            module_config = load(module_file)
            self.logger.debug("[%s] Loaded module config: %s" % (module, module_config))

        if 'depends' in module_config:
            for depend in module_config['depends']:
                if depend not in self['modules']:
                    print(self)
                    raise KeyError(f"Module '{depend}' not found in config")

        if 'custom_parameters' in module_config:
            self['custom_parameters'] = module_config['custom_parameters']
            self.logger.debug("[%s] Registered custom parameters: %s" % (module, module_config['custom_parameters']))

        if 'imports' in module_config:
            self['imports'] = module_config['imports']
            self.logger.debug("[%s] Registered imports: %s" % (module, self['imports']))

        for name, value in module_config.items():
            if name in ('custom_parameters', 'depends', 'imports'):
                self.logger.debug("[%s] Skipping '%s'" % (module, name))
                continue
            self.logger.debug("[%s] Setting '%s' to: %s" % (module, name, value))
            self[name] = value

        self['modules'].append(module)


@loggify
class InitramfsGenerator:
    __version__ = "0.4.0"

    def __init__(self, config='config.toml', out_dir='initramfs', clean=False, *args, **kwargs):
        self.config_filename = config
        self.out_dir = out_dir
        self.clean = clean
        self.build_pre = [self.generate_structure]
        self.build_tasks = [self.deploy_dependencies]
        self.config_dict = InitramfsConfigDict(logger=self.logger)

        self.init_types = ['init_pre', 'init_main', 'init_late', 'init_final']

        self.load_config()

    def load_config(self):
        """
        Loads the config from the specified toml file
        """
        with open(self.config_filename, 'rb') as config_file:
            self.logger.info("Loading config file: %s" % config_file.name)
            raw_config = load(config_file)

        # Process into the config dict, it should handle parsing
        for config, value in raw_config.items():
            self.logger.debug("Processing config key: %s" % config)
            self.config_dict[config] = value

        self.logger.debug("Loaded config: %s" % self.config_dict)

        for parameter in ['out_dir', 'clean']:
            setattr(self, parameter, self.config_dict.get(parameter, getattr(self, parameter)))

    def build_structure(self):
        """
        builds the initramfs structure
        """
        # If clean is set, clear the target build dir
        if self.clean:
            from shutil import rmtree
            from os.path import isdir
            # If the build dir is present, clean it, otherwise log and continue
            if isdir(self.out_dir):
                self.logger.warning("Cleaning build dir: %s" % self.out_dir)
                rmtree(self.out_dir)
            else:
                self.logger.info("Build dir is not present, not cleaning: %s" % self.out_dir)

        # Run pre-build tasks, by default just calls 'generate_structure'
        self.logger.info("Running pre build tasks")
        self.logger.debug(self.build_pre)
        for task in self.build_pre:
            task()

        # Run custom pre-build tasks imported from modules
        if 'build_pre' in self.config_dict['imports']:
            self.logger.info("Running custom pre build tasks")
            self.logger.debug(self.config_dict['imports']['build_pre'])
            for task in self.config_dict['imports']['build_pre']:
                task(self)

        # Run all build tasks, by default just calls 'deploy_dependencies'
        self.logger.info("Running build tasks")
        self.logger.debug(self.build_tasks)
        for task in self.build_tasks:
            task()

        # Run custom build tasks imported from modules
        if 'build_tasks' in self.config_dict['imports']:
            self.logger.info("Running custom build tasks")
            self.logger.debug(self.config_dict['imports']['build_tasks'])
            for task in self.config_dict['imports']['build_tasks']:
                task(self)

    def generate_init_main(self):
        """
        Generates the main init file, using everything but the pre portion
        """
        out = list()
        for init_type in self.init_types:
            if init_type != 'init_pre' and init_type != 'init_final':
                self.logger.info("Configuring init stage: %s" % init_type)
                out += ["\n\n# Begin %s" % init_type]
                for func in self.config_dict['imports'].get(init_type, []):
                    self.logger.info("Running init generator function: %s" % func.__name__)
                    out.extend(func(self))
        return out

    def generate_init(self):
        """
        Generates the init file
        """
        from os import chmod, chown
        self.logger.info("Running init generator functions")

        init = [self.config_dict['shebang']]

        init += ["# Generated by initramfs_generator.py v%s" % self.__version__]
        init += ["\n# Begin init_pre"]

        self.logger.info("Running init generator functions: init_pre")
        [init.extend(func(self)) for func in self.config_dict['imports'].get('init_pre')]

        if self.config_dict['imports'].get('custom_init'):
            self.logger.info("Running init generator functions: custom_init")
            init += ["\n\n# Begin custom_init"]
            [init.extend(func(self)) for func in self.config_dict['imports'].get('custom_init')]
        else:
            self.logger.info("Running init generator functions: init_main")
            init += self.generate_init_main()

        self.logger.info("Running init generator functions: init_final")
        init += ["\n\n# Begin init_final"]
        [init.extend(func(self)) for func in self.config_dict['imports'].get('init_final')]

        init += ["\n\n# END INIT"]

        init_path = Path(self.out_dir, 'init')
        with open(init_path, 'w', encoding='utf-8') as init_file:
            [init_file.write(f"{line}\n") for line in init]

        self.logger.info("Wrote init file: %s" % init_path)
        chmod(init_path, 0o755)
        self.logger.debug("Set init file permissions: %s" % oct(0o755))
        chown(init_path, self.config_dict['_file_owner_uid'], self.config_dict['_file_owner_uid'])
        self.logger.debug("Set init file owner: %s" % self.config_dict['_file_owner_uid'])

    def generate_structure(self):
        """
        Generates the initramfs directory structure
        """
        from os.path import isdir
        from os import makedirs, chown

        if not isdir(self.out_dir):
            makedirs(self.out_dir)
            self.logger.info("Created output directory: %s" % self.out_dir)
            chown(self.out_dir, self.config_dict['_file_owner_uid'], self.config_dict['_file_owner_uid'])
            self.logger.debug("Set output directory owner: %s" % self.config_dict['_file_owner_uid'])

        for subdir in set(self.config_dict['paths']):
            subdir_path = Path(subdir)
            subdir_relative_path = subdir_path.relative_to(subdir_path.anchor)
            target_dir = self.out_dir / subdir_relative_path

            self._mkdir(target_dir)

    def _mkdir(self, path):
        """
        Creates a directory, chowns it as self.config_dict['_file_owner_uid']
        """
        from os.path import isdir
        from os import mkdir, chown

        self.logger.debug("Creating directory for: %s" % path)

        if path.is_dir():
            path_dir = path.parent
            self.logger.debug("Directory path: %s" % path_dir)
        else:
            path_dir = path

        if not isdir(path_dir.parent):
            self.logger.info("Parent directory does not exist: %s" % path_dir.parent)
            self._mkdir(path_dir.parent)

        if not isdir(path_dir):
            mkdir(path)
            self.logger.info("Created directory: %s" % path)
            chown(path, self.config_dict['_file_owner_uid'], self.config_dict['_file_owner_uid'])
            self.logger.debug("Set directory owner: %s" % self.config_dict['_file_owner_uid'])
        else:
            self.logger.info("Directory already exists: %s" % path_dir)
            chown(path_dir, self.config_dict['_file_owner_uid'], self.config_dict['_file_owner_uid'])
            self.logger.debug("Set directory '%s' owner: %s" % (path_dir, self.config_dict['_file_owner_uid']))

    def _copy(self, source, dest):
        """
        Copies a file, chowns it as self.config_dict['_file_owner_uid']
        """
        from shutil import copy2
        from os import chown

        self.logger.info("Copying '%s' to '%s'" % (source, dest))
        copy2(source, dest)

        self.logger.debug("Setting ownership of '%s' to: %s" % (dest, self.config_dict['_file_owner_uid']))
        chown(dest, self.config_dict['_file_owner_uid'], self.config_dict['_file_owner_uid'])

    def deploy_dependencies(self):
        """
        Copies all required dependencies
        should be used after generate_structure
        """
        for dependency in self.config_dict['dependencies']:
            source_file_path = Path(dependency)
            dest_file_path = self.out_dir / source_file_path.relative_to(source_file_path.anchor)

            source_file_path.relative_to(source_file_path.anchor)

            self._mkdir(dest_file_path)
            self._copy(dependency, dest_file_path)

