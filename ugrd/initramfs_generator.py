
__author__ = "desultory"
__version__ = "0.7.0"

from tomllib import load
from pathlib import Path
from subprocess import run

from ugrd.zen_custom import loggify, handle_plural, NoDupFlatList


def calculate_dependencies(binary):
    from shutil import which

    binary_path = which(binary)
    if not binary_path:
        raise RuntimeError("'%s' not found in PATH" % binary)

    dependencies = run(['lddtree', '-l', binary_path], capture_output=True)
    if dependencies.returncode != 0:
        raise OSError(dependencies.stderr.decode('utf-8'))

    dependency_paths = []
    for dependency in dependencies.stdout.decode('utf-8').splitlines():
        # Remove extra slash at the start if it exists
        if dependency.startswith('//'):
            dependency = dependency[1:]

        dep_path = Path(dependency)
        dependency_paths.append(dep_path)

    return dependency_paths


@loggify
class InitramfsConfigDict(dict):
    """
    Dict for containing config for the InitramfsGenerator

    IMPORTANT:
        This dict does not act like a normal dict, setitem is designed to append when the overrides are used
        Default parameters are defined in builtin_parameters
    """
    __version__ = "0.6.7"

    builtin_parameters = {'binaries': NoDupFlatList,  # Binaries which should be included in the initramfs, dependencies are automatically calculated
                          'dependencies': NoDupFlatList,  # Raw dependencies, files which should be included in the initramfs
                          'mod_depends': NoDupFlatList,  # Modules required by other modules, will be re-checked calling .verify_deps()
                          'paths': NoDupFlatList,  # Paths which will be created in the initramfs
                          'modules': NoDupFlatList,  # A list of the names of modules which have been loaded, mostly used for dependency checking
                          'mounts': dict,  # A dict of Mount objects
                          'imports': dict,  # A dict of functions to be imported into the initramfs, under their respective hooks
                          'mask': dict,  # A dict of imported functions to be masked
                          'custom_parameters': dict,  # Custom parameters loaded from imports
                          'custom_processing': dict}  # Custom processing functions which will be run to validate and process parameters

    def __init__(self, *args, **kwargs):
        # Define the default parameters
        for parameter, default_type in self.builtin_parameters.items():
            if default_type == NoDupFlatList:
                super().__setitem__(parameter, default_type(no_warn=True, log_bump=5, logger=self.logger, _log_init=False))
            else:
                super().__setitem__(parameter, default_type())

    def __setitem__(self, key, value):
        # If the type is registered, use the appropriate update function
        if expected_type := self.builtin_parameters.get(key, self['custom_parameters'].get(key)):
            if hasattr(self, f"_process_{key}"):
                self.logger.debug("Using builtin setitem for: %s" % key)
                getattr(self, f"_process_{key}")(value)
            elif func := self['custom_processing'].get(f"_process_{key}"):
                self.logger.debug("Using custom setitem for: %s" % key)
                func(self, value)
            elif func := self['custom_processing'].get(f"_process_{key}_multi"):
                self.logger.debug("Using custom plural setitem for: %s" % key)
                handle_plural(func)(self, value)
            elif expected_type in (list, NoDupFlatList):
                self.logger.debug("Using list setitem for: %s" % key)
                self[key].append(value)
            elif expected_type == dict:
                self.logger.debug("Using dict setitem for: %s" % key)
                if key not in self:
                    self.logger.debug("Setting dict '%s' to: %s" % (key, value))
                    super().__setitem__(key, value)
                else:
                    self.logger.debug("Updating dict '%s' with: %s" % (key, value))
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
        self.logger.debug("Registered custom parameter '%s' with type: %s" % (parameter_name, parameter_type))

        if parameter_type == "NoDupFlatList":
            super().__setitem__(parameter_name, NoDupFlatList(no_warn=True, log_bump=5, logger=self.logger, _log_init=False))
        elif parameter_type in ("list", "dict"):
            super().__setitem__(parameter_name, eval(parameter_type)())
        elif parameter_type == "bool":
            super().__setitem__(parameter_name, False)

    @handle_plural
    def _process_binaries(self, binary):
        """
        processes passed binary(ies) into the 'binaries' list
        updates the dependencies using the passed binary name
        """
        self.logger.debug("Calculating dependencies for: %s" % binary)
        try:
            dependencies = calculate_dependencies(binary)
            self.logger.debug("[%s] Dependencies: %s" % (binary, dependencies))
        except OSError as e:
            raise RuntimeError("Failed to calculate dependencies for '%s': %s" % (binary, e))

        self['dependencies'] += dependencies
        # Append, don't set or it will recursively call this function
        self['binaries'].append(binary)

    @handle_plural
    def _process_imports(self, import_type: str, import_value: dict):
        """
        Processes imports in a module, importing the functions and adding them to the appropriate list
        """
        self.logger.debug("Processing imports of type: %s" % import_type)

        from importlib import import_module
        for module_name, function_names in import_value.items():
            self.logger.debug("Importing module: %s" % module_name)
            function_list = [getattr(import_module(f"{module_name}"), function_name) for function_name in function_names]

            if import_type not in self['imports']:
                self.logger.debug("Creating import type: %s" % import_type)
                self['imports'][import_type] = NoDupFlatList(log_bump=10, logger=self.logger, _log_init=False)

            self['imports'][import_type] += function_list
            self.logger.debug("Updated import '%s': %s" % (import_type, function_list))

            if import_type == 'config_processing':
                for function in function_list:
                    self['custom_processing'][function.__name__] = function
                    self.logger.debug("Registered config processing function: %s" % function.__name__)

    @handle_plural
    def _process_mod_depends(self, module):
        """
        Processes module dependencies
        """
        self.logger.debug("Processing module dependency: %s" % module)
        if module not in self['modules']:
            self.logger.warning("Module depenncy added, but required dependency is not loaded: %s" % module)

        self['mod_depends'].append(module)

    def verify_deps(self):
        """ Verifies that all module dependencies are met """
        for module in self['mod_depends']:
            if module not in self['modules']:
                raise KeyError(f"Required module '{module}' not found in config")

        self.logger.info("Verified module depndencies: %s" % self['mod_depends'])

    def verify_mask(self):
        """
        Processes masked imports
        """
        for mask_hook, mask_items in self['mask'].items():
            if self['imports'].get(mask_hook):
                for function in self['imports'][mask_hook]:
                    if function.__name__ in mask_items:
                        self.logger.warning("Masking import: %s" % function.__name__)
                        self['imports'][mask_hook].remove(function)

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

        if 'mod_depends' in module_config:
            self['mod_depends'] = module_config['mod_depends']

        if 'custom_parameters' in module_config:
            self['custom_parameters'] = module_config['custom_parameters']
            self.logger.debug("[%s] Registered custom parameters: %s" % (module, module_config['custom_parameters']))

        if 'imports' in module_config:
            self['imports'] = module_config['imports']
            self.logger.debug("[%s] Registered imports: %s" % (module, self['imports']))

        for name, value in module_config.items():
            if name in ('custom_parameters', 'mod_depends', 'imports'):
                self.logger.debug("[%s] Skipping '%s'" % (module, name))
                continue
            self.logger.debug("[%s] Setting '%s' to: %s" % (module, name, value))
            self[name] = value

        self['modules'].append(module)


@loggify
class InitramfsGenerator:
    __version__ = "0.5.0"

    def __init__(self, config='config.toml', *args, **kwargs):
        self.config_filename = config
        self.build_pre = [self.generate_structure]
        self.build_tasks = [self.deploy_dependencies]
        self.config_dict = InitramfsConfigDict(logger=self.logger)

        # init_pre and init_final are run as part of generate_initramfs_main
        self.init_types = ['init_main', 'init_late', 'init_mount']

        self.load_config()
        self.config_dict.verify_deps()
        self.config_dict.verify_mask()

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
            dict_value = self.config_dict[parameter]
            if dict_value is not None:
                setattr(self, parameter, dict_value)
            else:
                raise KeyError("Required parameter '%s' not found in config" % parameter)

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
        else:
            self.logger.info("Not cleaning build dir: %s" % self.out_dir)

        # Run pre-build tasks, by default just calls 'generate_structure'
        self.logger.info("Running pre build tasks")
        self.logger.debug(self.build_pre)
        for task in self.build_pre:
            task()

        # Run custom pre-build tasks imported from modules
        if build_pre := self.config_dict['imports'].get('build_pre'):
            self.logger.info("Running custom pre build tasks")
            self.logger.debug(build_pre)
            for task in build_pre:
                task(self)

        # Run all build tasks, by default just calls 'deploy_dependencies'
        self.logger.info("Running build tasks")
        self.logger.debug(self.build_tasks)
        for task in self.build_tasks:
            task()

        # Run custom build tasks imported from modules
        if build_tasks := self.config_dict['imports'].get('build_tasks'):
            self.logger.info("Running custom build tasks")
            self.logger.debug(build_tasks)
            for task in build_tasks:
                task(self)

    def generate_init_main(self):
        """
        Generates the main init file.
        """
        out = list()

        for init_type in self.init_types:
            out += self._run_hook(init_type)

        return out

    def _run_hook(self, level):
        """
        Runs an init hook
        """
        self.logger.info("Running init level: %s" % level)
        out = ['\n\n# Begin %s' % level]
        for func in self.config_dict['imports'].get(level):
            self.logger.info("Running init generator function: %s" % func.__name__)
            if function_output := func(self):
                if isinstance(function_output, str):
                    self.logger.debug("[%s] Function returned string: %s" % (func.__name__, function_output))
                    out += [function_output]
                else:
                    self.logger.debug("[%s] Function returned output: %s" % (func.__name__, function_output))
                    out.extend(function_output)
            else:
                self.logger.warning("Function returned no output: %s" % func.__name__)
        return out

    def generate_init(self):
        """
        Generates the init file
        """
        self.logger.info("Running init generator functions")

        init = [self.config_dict['shebang']]

        init += ["# Generated by initramfs_generator.py v%s" % self.__version__]

        init += self._run_hook('init_pre')
        init += self._run_hook('custom_init') if self.config_dict['imports'].get('custom_init') else self.generate_init_main()
        init += self._run_hook('init_final')

        init += ["\n\n# END INIT"]

        self._write('init', init, 0o755)

        self.logger.debug("Final config: %s" % self.config_dict)

    def generate_structure(self):
        """
        Generates the initramfs directory structure
        """
        from os.path import isdir

        if not isdir(self.out_dir):
            self._mkdir(self.out_dir)

        for subdir in set(self.config_dict['paths']):
            subdir_path = Path(subdir)
            subdir_relative_path = subdir_path.relative_to(subdir_path.anchor)
            target_dir = self.out_dir / subdir_relative_path

            self._mkdir(target_dir)

    def pack(self):
        """
        Packs the initramfs based on self.config_dict['imports']['pack']
        """
        if pack_funcs := self.config_dict['imports'].get('pack'):
            self.logger.info("Running custom pack functions")
            self.logger.debug(pack_funcs)
            for func in pack_funcs:
                func(self)
        else:
            self.logger.info("No custom pack functions found, skipping")

    def _mkdir(self, path):
        """
        Creates a directory, chowns it as self.config_dict['_file_owner_uid']
        """
        from os.path import isdir
        from os import mkdir

        self.logger.debug("Creating directory for: %s" % path)

        if path.is_dir():
            path_dir = path.parent
            self.logger.debug("Directory path: %s" % path_dir)
        else:
            path_dir = path

        if not isdir(path_dir.parent):
            self.logger.debug("Parent directory does not exist: %s" % path_dir.parent)
            self._mkdir(path_dir.parent)

        if not isdir(path_dir):
            mkdir(path)
            self.logger.info("Created directory: %s" % path)
        else:
            self.logger.debug("Directory already exists: %s" % path_dir)

        self._chown(path_dir)

    def _chown(self, path):
        """
        Chowns a file or directory as self.config_dict['_file_owner_uid']
        """
        from os import chown

        if path.owner() == self.config_dict['_file_owner_uid'] and path.group() == self.config_dict['_file_owner_uid']:
            self.logger.debug("File '%s' already owned by: %s" % (path, self.config_dict['_file_owner_uid']))
            return

        chown(path, self.config_dict['_file_owner_uid'], self.config_dict['_file_owner_uid'])
        if path.is_dir():
            self.logger.debug("[%s] Set directory owner: %s" % (path, self.config_dict['_file_owner_uid']))
        else:
            self.logger.debug("[%s] Set file owner: %s" % (path, self.config_dict['_file_owner_uid']))

    def _write(self, file_name, contents, chmod_mask=0o644, in_build_dir=True):
        """
        Writes a file and owns it as self.config_dict['_file_owner_uid']
        Sets the passed chmod
        """
        from os import chmod

        if in_build_dir:
            if file_name.startswith('/'):
                file_path = self.config_dict['out_dir'] / Path(file_name).relative_to('/')
            else:
                file_path = self.config_dict['out_dir'] / file_name
        else:
            file_path = Path(file_name)

        self.logger.debug("[%s] Writing contents: %s: " % (file_path, contents))
        with open(file_path, 'w') as file:
            file.writelines("\n".join(contents))

        self.logger.info("Wrote file: %s" % file_path)
        chmod(file_path, chmod_mask)
        self.logger.debug("[%s] Set file permissions: %s" % (file_path, chmod_mask))

        self._chown(file_path)

    def _copy(self, source, dest=None, in_build_dir=True):
        """
        Copies a file, chowns it as self.config_dict['_file_owner_uid']
        """
        from shutil import copy2

        if not isinstance(source, Path):
            source = Path(source)

        if not dest:
            self.logger.debug("No destination specified, using source: %s" % source)
            dest = source
        elif not isinstance(dest, Path):
            dest = Path(dest)

        if in_build_dir:
            if dest.is_absolute():
                dest_path = self.config_dict['out_dir'] / Path(dest).relative_to('/')
            else:
                dest_path = self.config_dict['out_dir'] / dest
        else:
            dest_path = Path(dest)

        if not dest_path.parent.is_dir():
            self.logger.debug("Parent directory for '%s' does not exist: %s" % (dest_path.name, dest.parent))
            self._mkdir(dest_path.parent)

        if dest_path.is_file():
            self.logger.warning("File already exists: %s" % dest_path)
        self.logger.info("Copying '%s' to '%s'" % (source, dest_path))
        copy2(source, dest_path)

        self._chown(dest_path)

    def _run(self, args):
        """
        Runs a command, returns the object
        """
        self.logger.debug("Running command: %s" % args)
        cmd = run(args, capture_output=True)
        if cmd.returncode != 0:
            self.logger.error("Failed to run command: %s" % cmd.args)
            self.logger.error("Command output: %s" % cmd.stdout.decode('utf-8'))
            self.logger.error("Command error: %s" % cmd.stderr.decode('utf-8'))
            raise RuntimeError("Failed to run command: %s" % cmd.args)

        return cmd

    def deploy_dependencies(self):
        """
        Copies all required dependencies
        should be used after generate_structure
        """
        for dependency in self.config_dict['dependencies']:
            self.logger.debug("Deploying dependency: %s" % dependency)
            self._copy(dependency)
