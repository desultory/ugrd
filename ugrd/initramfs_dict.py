
__author__ = "desultory"
__version__ = "0.7.1"

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
    def _process_dependencies(self, dependency):
        """
        Checks if a dependency exists before adding it to the list
        """
        if not isinstance(dependency, Path):
            self.logger.debug("Converting dependency '%s' to Path" % dependency)
            dependency = Path(dependency)

        if not dependency.exists():
            raise FileNotFoundError(dependency)

        self['dependencies'].append(dependency)

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

        self['dependencies'] = dependencies
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

        module_path = Path(__file__).parent.parent / (module.replace('.', '/') + '.toml')
        self.logger.debug("Module path: %s" % module_path)

        with open(module_path, 'rb') as module_file:
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

