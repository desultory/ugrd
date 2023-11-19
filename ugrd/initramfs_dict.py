
__author__ = "desultory"
__version__ = "0.9.0"

from tomllib import load, TOMLDecodeError
from pathlib import Path

from ugrd.zen_custom import loggify, handle_plural, NoDupFlatList, pretty_print


@loggify
class InitramfsConfigDict(dict):
    """
    Dict for containing config for the InitramfsGenerator

    IMPORTANT:
        This dict does not act like a normal dict, setitem is designed to append when the overrides are used
        Default parameters are defined in builtin_parameters
    """
    builtin_parameters = {'mod_depends': NoDupFlatList,  # Modules required by other modules, will be re-checked calling .verify_deps()
                          'modules': NoDupFlatList,  # A list of the names of modules which have been loaded, mostly used for dependency checking
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

    def import_args(self, args: dict):
        """
        Imports data from an argument dict
        """
        for arg, value in args.items():
            self.logger.warning("Importing argument '%s' with value: %s" % (arg, value))
            self[arg] = value

    def __setitem__(self, key, value):
        # If the type is registered, use the appropriate update function
        if expected_type := self.builtin_parameters.get(key, self['custom_parameters'].get(key)):
            self.logger.log(5, "[%s] Expected type: %s" % (key, expected_type))
            if hasattr(self, f"_process_{key}"):
                self.logger.log(5, "[%s] Using builtin setitem: %s" % (key, f"_process_{key}"))
                getattr(self, f"_process_{key}")(value)
            elif func := self['custom_processing'].get(f"_process_{key}"):
                self.logger.log(5, "[%s] Using custom setitem: %s" % (key, func.__name__))
                func(self, value)
            elif func := self['custom_processing'].get(f"_process_{key}_multi"):
                self.logger.log(5, "[%s] Using custom plural setitem: %s" % (key, func.__name__))
                handle_plural(func)(self, value)
            elif expected_type in (list, NoDupFlatList):
                self.logger.log(5, "Using list setitem for: %s" % key)
                self[key].append(value)
            elif expected_type == dict:
                if key not in self:
                    self.logger.log(5, "Setting dict '%s' to: %s" % (key, value))
                    super().__setitem__(key, value)
                else:
                    self.logger.log(5, "Updating dict '%s' with: %s" % (key, value))
                    self[key].update(value)
            else:
                super().__setitem__(key, expected_type(value))
        else:  # Otherwise set it like a normal dict item
            self.logger.debug("[%s] Unable to determine expected type, valid builtin types: %s" % (key, self.builtin_parameters.keys()))
            self.logger.debug("[%s] Custom types: %s" % (key, self['custom_parameters'].keys()))
            if key.startswith('_'):
                self.logger.warning("Setting unknown internal paramaters '%s' with value: %s" % (key, value))
            else:
                raise ValueError("Detected undefined parameter type '%s' with value: %s" % (key, value))

    @handle_plural
    def _process_custom_parameters(self, parameter_name, parameter_type):
        """
        Updates the custom_parameters attribute.
        Sets the initial value of the parameter based on the type.
        """
        self['custom_parameters'][parameter_name] = eval(parameter_type)
        self.logger.debug("Registered custom parameter '%s' with type: %s" % (parameter_name, parameter_type))

        if parameter_type == "NoDupFlatList":
            super().__setitem__(parameter_name, NoDupFlatList(no_warn=True, log_bump=5, logger=self.logger, _log_init=False))
        elif parameter_type in ("list", "dict"):
            super().__setitem__(parameter_name, eval(parameter_type)())
        elif parameter_type == "bool":
            super().__setitem__(parameter_name, False)
        elif parameter_type == "int":
            super().__setitem__(parameter_name, 0)

    @handle_plural
    def _process_imports(self, import_type: str, import_value: dict):
        """
        Processes imports in a module, importing the functions and adding them to the appropriate list
        """
        from importlib import import_module

        self.logger.debug("Processing imports of type: %s" % import_type)

        for module_name, function_names in import_value.items():
            self.logger.debug("Importing module: %s" % module_name)

            module = import_module(module_name)
            self.logger.log(5, "[%s] Imported module contents: %s" % (module_name, dir(module)))
            if '_module_name' in dir(module) and module._module_name != module_name:
                self.logger.warning("Module name mismatch: %s != %s" % (module._module_name, module_name))

            function_list = [getattr(module, function_name) for function_name in function_names]

            if import_type not in self['imports']:
                self.logger.log(5, "Creating import type: %s" % import_type)
                self['imports'][import_type] = NoDupFlatList(log_bump=10, logger=self.logger, _log_init=False)

            self['imports'][import_type] += function_list
            self.logger.debug("[%s] Updated import functions: %s" % (import_type, function_list))

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

    @handle_plural
    def _process_modules(self, module):
        """
        processes a single module into the config
        takes list with decorator
        """
        if module in self['modules']:
            self.logger.warning("Module '%s' already loaded" % module)
            return

        self.logger.debug("Processing module: %s" % module)

        module_path = Path(__file__).parent.parent / (module.replace('.', '/') + '.toml')
        self.logger.debug("Module path: %s" % module_path)

        with open(module_path, 'rb') as module_file:
            try:
                module_config = load(module_file)
            except TOMLDecodeError as e:
                raise TOMLDecodeError("Unable to load module config: %s" % module) from e

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

    def __str__(self):
        return pretty_print(self)
