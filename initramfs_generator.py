from subprocess import run
from yaml import safe_load

from zen_custom import class_logger, handle_plural


def calculate_dependencies(binary):
    binary_path = run(['which', binary], capture_output=True).stdout.decode('utf-8').strip()
    dependencies = run(['lddtree', '-l', binary_path], capture_output=True)
    if dependencies.returncode != 0:
        raise OSError(dependencies.stderr.decode('utf-8'))
    return dependencies.stdout.decode('utf-8').splitlines()


@class_logger
class InitramfsConfigDict(dict):
    """
    Dict for containing config for the InitramfsGenerator

    IMPORTANT:
        This dict does not act like a normal dict, setitem is designed to append when the overrides are used
        These overrides exist for binaries, dependencies, and modules
    """
    builtin_parameters = {'binaries': list,
                          'dependencies': list,
                          'paths': list,
                          'modules': list,
                          'mounts': dict,
                          'imports': dict}

    def __init__(self, *args, **kwargs):
        for parameter, default_type in self.builtin_parameters.items():
            super().__setitem__(parameter, default_type())

    def __setitem__(self, key, value):
        if key in self.builtin_parameters:
            if self.builtin_parameters[key] is list:
                self.update_list(key, value)
            elif self.builtin_parameters[key] is dict:
                self.update_dict(key, value)
            elif self.builtin_parameters[key] is str:
                super().__setitem(key, value)
        else:
            self.logger.warning("Detected custom type '%s' with value: %s" % (key, value))
            super().__setitem__(key, value)

        if hasattr(self, f"_process_{key}"):
            self.logger.debug("Using custom setitem for: %s" % key)
            getattr(self, f"_process_{key}")(value)
        elif 'config_processing' in self['imports']:
            for func in self['imports']['config_processing']:
                if func.__name__ == f"_process_{key}":
                    self.logger.debug("Using imported setitem for: %s" % key)
                    handle_plural(func)(self, value)

    @handle_plural
    def update_dict(self, name: str, key: str, value: dict):
        """
        Updates a dict in the internal dictionary
        """
        if key not in self[name]:
            self[name][key] = value
            self.logger.info("Set %s[%s] to: %s" % (name, key, value))
        else:
            self.logger.warning("%s[%s] already set" % (name, key))

    @handle_plural
    def update_list(self, name: str, value: str):
        """
        Updates a list in the internal dictionary
        """
        if value not in self[name]:
            self[name].append(value)
            self.logger.info("Added '%s' to %s" % (value, name))
        else:
            self.logger.warning("%s already defined: %s" % (name, value))

    @handle_plural
    def _process_binaries(self, binary):
        """
        processes passed binary(ies) into the 'binaries' list
        then updates the dependencies using the passed binary name
        """
        self.logger.debug("Calculating dependencies for: %s" % binary)
        self['dependencies'] = calculate_dependencies(binary)

    @handle_plural
    def _process_imports(self, import_type: str, import_value: dict):
        """
        Processes imports in a module
        """
        from importlib import import_module
        for module_name, function_names in import_value.items():
            function_list = [getattr(import_module(f"{module_name}"), function_name) for function_name in function_names]
            if not isinstance(self['imports'][import_type], list):
                self['imports'][import_type] = list()
            self['imports'][import_type] += function_list
            self.logger.info("Updated import '%s': %s" % (import_type, function_list))

    @handle_plural
    def _process_modules(self, module):
        """
        processes a single module into the config
        takes list with decorator
        """
        with open(f"{module.replace('.', '/')}.yaml", 'r') as module_file:
            module_config = safe_load(module_file)
        if 'binaries' not in module_config:
            self.logger.warning("No binaries passed as part of module: %s" % module_config)
        # Call it this way to use the override function
        for name, value in module_config.items():
            self[name] = value


@class_logger
class InitramfsGenerator:
    def __init__(self, config='config.yaml', out_dir='initramfs', clean=False, *args, **kwargs):
        self.config_filename = config
        self.out_dir = out_dir
        self.clean = clean
        self.pre_build = [self.generate_structure]
        self.build_tasks = [self.deploy_dependencies]
        self.config_dict = InitramfsConfigDict()

        self.init_types = ['init_pre', 'init_main', 'init_late', 'init_final']

        self.load_config()
        self.build_structure()
        self.generate_init()

    def load_config(self):
        """
        Loads the config from the specified yaml file
        """
        with open(self.config_filename, 'r') as config_file:
            self.logger.info("Loading config file: %s" % config_file.name)
            raw_config = safe_load(config_file)

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
        if self.clean:
            from shutil import rmtree
            from os.path import isdir
            if isdir(self.out_dir):
                self.logger.warning("Cleaning build dir: %s" % self.out_dir)
                rmtree(self.out_dir)
            else:
                self.logger.info("Build dir is not present, not cleaning: %s" % self.out_dir)

        self.logger.info("Running pre build tasks")
        self.logger.debug(self.pre_build)
        for task in self.pre_build:
            task()

        self.logger.info("Running build tasks")
        self.logger.debug(self.build_tasks)
        for task in self.build_tasks:
            task()

        if 'build_tasks' in self.config_dict['imports']:
            for task in self.config_dict['imports']['build_tasks']:
                task(self)

    def generate_init_main(self):
        """
        Generates the main init file, using everything but the pre portion
        """
        out = list()
        for init_type in self.init_types:
            self.logger.info("Configuring init stage: %s" % init_type)
            if init_type != 'init_pre' and init_type != 'init_final':
                [out.extend(func(self)) for func in self.config_dict['imports'].get(init_type, [])]
        return out

    def generate_init(self):
        """
        Generates the init file
        """
        from os import chmod
        init = [self.config_dict['shebang']]
        [init.extend(func(self)) for func in self.config_dict['imports'].get('init_pre')]
        if self.config_dict['imports'].get('custom_init'):
            [init.extend(func(self)) for func in self.config_dict['imports'].get('custom_init')]
        else:
            init += self.generate_init_main()
        [init.extend(func(self)) for func in self.config_dict['imports'].get('init_final')]
        with open(f"{self.out_dir}/init", 'w', encoding='utf-8') as init_file:
            [init_file.write(f"{line}\n") for line in init]
        chmod(f"{self.out_dir}/init", 0o755)

    def generate_structure(self):
        """
        Generates the initramfs directory structure
        """
        from os.path import isdir
        from os import makedirs
        if not isdir(self.out_dir):
            makedirs(self.out_dir)
            self.logger.info("Created output directory: %s" % self.out_dir)

        for subdir in set(self.config_dict['paths'] + list(self.config_dict['mounts'].keys())):
            target_dir = f"{self.out_dir}/{subdir}"
            if not isdir(target_dir):
                makedirs(target_dir)
                self.logger.info("Created subdirectory: %s" % target_dir)

    def deploy_dependencies(self):
        """
        Copies all required dependencies
        should be used after generate_structure
        """
        from shutil import copy2
        for dependency in self.config_dict['dependencies']:
            dest_file = f"{self.out_dir}{dependency}"
            copy2(dependency, dest_file)
            self.logger.info("Copied '%s' to: %s" % (dependency, dest_file))

