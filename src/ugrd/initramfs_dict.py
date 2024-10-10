__author__ = "desultory"
__version__ = "2.2.1"

from tomllib import load, TOMLDecodeError
from pathlib import Path
from queue import Queue
from collections import UserDict

from zenlib.logging import loggify
from zenlib.util import handle_plural, pretty_print, NoDupFlatList


@loggify
class InitramfsConfigDict(UserDict):
    """
    Dict for ugrd config

    IMPORTANT!!!:
        This dict does not act like a normal dict, setitem is designed to append when the overrides are used
        Default parameters are defined in builtin_parameters

    By default ugrd.base.base is loaded, which is a very minimal config.
    If NO_BASE is set to True, ugrd.base.core is loaded instead, which contains absolute essentials.

    If parameters which are not registerd are set, they are added to the processing queue and processed when the type is known.
    """
    builtin_parameters = {'modules': NoDupFlatList,  # A list of the names of modules which have been loaded, mostly used for dependency checking
                          'imports': dict,  # A dict of functions to be imported into the initramfs, under their respective hooks
                          'validated': bool,  # A flag to indicate if the config has been validated, mostly used for log levels
                          'custom_parameters': dict,  # Custom parameters loaded from imports
                          'custom_processing': dict,  # Custom processing functions which will be run to validate and process parameters
                          '_processing': dict}  # A dict of queues containing parameters which have been set before the type was known

    def __init__(self, NO_BASE=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Define the default parameters
        for parameter, default_type in self.builtin_parameters.items():
            if default_type == NoDupFlatList:
                self.data[parameter] = default_type(no_warn=True, log_bump=5, logger=self.logger, _log_init=False)
            else:
                self.data[parameter] = default_type()
        if not NO_BASE:
            self['modules'] = 'ugrd.base.base'
        else:
            self['modules'] = 'ugrd.base.core'

    def import_args(self, args: dict) -> None:
        """ Imports data from an argument dict. """
        for arg, value in args.items():
            self.logger.info("Importing argument '%s' with value: %s" % (arg, value))
            if arg == 'modules':  # allow loading modules by name from the command line
                for module in value.split(','):
                    self[arg] = module
            else:
                self[arg] = value

    def __setitem__(self, key: str, value) -> None:
        if self['validated']:
            return self.logger.error("[%s] Config is validatied, refusing to set value: %s" % (key, value))
        # If the type is registered, use the appropriate update function
        if any(key in d for d in (self.builtin_parameters, self['custom_parameters'])):
            return self.handle_parameter(key, value)
        else:
            self.logger.debug("[%s] Unable to determine expected type, valid builtin types: %s" % (key, self.builtin_parameters.keys()))
            self.logger.debug("[%s] Custom types: %s" % (key, self['custom_parameters'].keys()))
            # for anything but the logger, add to the processing queue
            if key != 'logger':
                self.logger.debug("Adding unknown internal parameter to processing queue: %s" % key)
                if key not in self['_processing']:
                    self['_processing'][key] = Queue()
                self['_processing'][key].put(value)

    def handle_parameter(self, key: str, value) -> None:
        """
        Handles a config parameter, setting the value and processing it if the type is known.
        Raises a KeyError if the parameter is not registered.

        Uses custom processing functions if they are defined, otherwise uses the standard setters.
        """
        # Get the expected type, first searching builtin_parameters, then custom_parameters
        for d in (self.builtin_parameters, self['custom_parameters']):
            expected_type = d.get(key)
            if expected_type:
                if expected_type.__name__ == "InitramfsGenerator":
                    self.data[key] = value
                    return self.logger.debug("Setting InitramfsGenerator: %s" % key)
                break  # Break and raise an exception if the type is not found
        else:
            raise KeyError("Parameter not registered: %s" % key)

        if hasattr(self, f"_process_{key}"):  # The builtin function is decorated and can handle plural
            self.logger.log(5, "[%s] Using builtin setitem: %s" % (key, f"_process_{key}"))
            return getattr(self, f"_process_{key}")(value)

        # Don't use masked processing functions for custom values, fall back to standard setters
        def check_mask(import_name: str) -> bool:
            """ Checks if the funnction is masked. """
            return import_name in self.get('masks', [])

        if func := self['custom_processing'].get(f"_process_{key}"):
            if check_mask(func.__name__):
                self.logger.debug("Skipping masked function: %s" % func.__name__)
            else:
                self.logger.log(5, "[%s] Using custom setitem: %s" % (key, func.__name__))
                return func(self, value)

        if func := self['custom_processing'].get(f"_process_{key}_multi"):
            if check_mask(func.__name__):
                self.logger.debug("Skipping masked function: %s" % func.__name__)
            else:
                self.logger.log(5, "[%s] Using custom plural setitem: %s" % (key, func.__name__))
                return handle_plural(func)(self, value)

        if expected_type in (list, NoDupFlatList):  # Append to lists, don't replace
            self.logger.log(5, "Using list setitem for: %s" % key)
            return self[key].append(value)

        if expected_type == dict:  # Create new keys, update existing
            if key not in self:
                self.logger.log(5, "Setting dict '%s' to: %s" % (key, value))
                return super().__setitem__(key, value)
            else:
                self.logger.log(5, "Updating dict '%s' with: %s" % (key, value))
                return self[key].update(value)

        self.logger.debug("Setting custom parameter: %s" % key)
        self.data[key] = expected_type(value)  # For everything else, simply set it

    @handle_plural
    def _process_custom_parameters(self, parameter_name: str, parameter_type: type) -> None:
        """
        Updates the custom_parameters attribute.
        Sets the initial value of the parameter based on the type.
        """
        from pycpio import PyCPIO

        self['custom_parameters'][parameter_name] = eval(parameter_type)
        self.logger.debug("Registered custom parameter '%s' with type: %s" % (parameter_name, parameter_type))

        match parameter_type:
            case "NoDupFlatList":
                self.data[parameter_name] = NoDupFlatList(no_warn=True, log_bump=5, logger=self.logger, _log_init=False)
            case "list" | "dict":
                self.data[parameter_name] = eval(parameter_type)()
            case "bool":
                self.data[parameter_name] = False
            case "int":
                self.data[parameter_name] = 0
            case "float":
                self.data[parameter_name] = 0.0
            case "str":
                self.data[parameter_name] = ""
            case "Path":
                self.data[parameter_name] = Path()
            case "PyCPIO":
                self.data[parameter_name] = PyCPIO(logger=self.logger, _log_init=False, _log_bump=10)
            case _:  # For strings and things, don't init them so they are None
                self.logger.warning("Leaving '%s' as None" % parameter_name)
                self.data[parameter_name] = None

    def _process_unprocessed(self, parameter_name: str) -> None:
        """ Processes queued values for a parameter. """
        if parameter_name not in self['_processing']:
            self.logger.log(5, "No queued values for: %s" % parameter_name)
            return

        value_queue = self['_processing'].pop(parameter_name)
        while not value_queue.empty():
            value = value_queue.get()
            if self['validated']:  # Log at info level if the config has been validated
                self.logger.info("[%s] Processing queued value: %s" % (parameter_name, value))
            else:
                self.logger.debug("[%s] Processing queued value: %s" % (parameter_name, value))
            self[parameter_name] = value

    @handle_plural
    def _process_imports(self, import_type: str, import_value: dict) -> None:
        """ Processes imports in a module, importing the functions and adding them to the appropriate list. """
        from importlib import import_module
        from importlib.util import spec_from_file_location, module_from_spec

        for module_name, function_names in import_value.items():
            self.logger.debug("[%s]<%s> Importing module functions : %s" % (module_name, import_type, function_names))
            try:
                module = import_module(module_name)
            except ModuleNotFoundError as e:
                module_path = Path('/var/lib/ugrd/' + module_name.replace('.', '/')).with_suffix('.py')
                self.logger.debug("Attempting to sideload module from: %s" % module_path)
                if not module_path.exists():
                    raise ModuleNotFoundError("Module not found: %s" % module_name) from e
                try:
                    spec = spec_from_file_location(module_name, module_path)
                    module = module_from_spec(spec)
                    spec.loader.exec_module(module)
                except Exception as e:
                    raise ModuleNotFoundError("Unable to load module: %s" % module_name) from e

            self.logger.log(5, "[%s] Imported module contents: %s" % (module_name, dir(module)))
            if '_module_name' in dir(module) and module._module_name != module_name:
                self.logger.warning("Module name mismatch: %s != %s" % (module._module_name, module_name))

            function_list = [getattr(module, function_name) for function_name in function_names]

            if import_type not in self['imports']:
                self.logger.log(5, "Creating import type: %s" % import_type)
                self['imports'][import_type] = NoDupFlatList(log_bump=10, logger=self.logger, _log_init=False)

            if import_type == 'custom_init':
                if self['imports']['custom_init']:
                    raise ValueError("Custom init function already defined: %s" % self['imports']['custom_init'])
                else:
                    self['imports']['custom_init'] = function_list[0]
                    self.logger.info("Registered custom init function: %s" % function_list[0].__name__)
                    continue

            if import_type == 'funcs':
                for function in function_list:
                    if function.__name__ in self['imports']['funcs']:
                        raise ValueError("Function '%s' already registered" % function.__name__)
                    if function.__name__ in self['binaries']:
                        raise ValueError("Function collides with defined binary: %s'" % function.__name__)

            self['imports'][import_type] += function_list
            self.logger.debug("[%s] Updated import functions: %s" % (import_type, function_list))

            if import_type == 'config_processing':
                for function in function_list:
                    self['custom_processing'][function.__name__] = function
                    self.logger.debug("Registered config processing function: %s" % function.__name__)
                    self._process_unprocessed(function.__name__.removeprefix('_process_'))

    @handle_plural
    def _process_modules(self, module: str) -> None:
        """
        processes a single module into the config
        takes list with decorator
        """
        if module in self['modules']:
            self.logger.debug("Module '%s' already loaded" % module)
            return

        self.logger.info("Processing module: %s" % module)

        module_subpath = module.replace('.', '/') + '.toml'

        module_path = Path(__file__).parent.parent / module_subpath
        if not module_path.exists():
            module_path = Path('/var/lib/ugrd') / module_subpath
            if not module_path.exists():
                raise FileNotFoundError("Unable to locate module: %s" % module)
        self.logger.debug("Module path: %s" % module_path)

        with open(module_path, 'rb') as module_file:
            try:
                module_config = load(module_file)
            except TOMLDecodeError as e:
                raise TOMLDecodeError("Unable to load module config: %s" % module) from e

        if imports := module_config.get('imports'):
            self.logger.debug("[%s] Processing imports: %s" % (module, imports))
            self['imports'] = imports

        custom_parameters = module_config.get('custom_parameters', {})
        if custom_parameters:
            self.logger.debug("[%s] Processing custom parameters: %s" % (module, custom_parameters))
            self['custom_parameters'] = custom_parameters

        for name, value in module_config.items():  # Process config values, in order they are defined
            if name in ['imports', 'custom_parameters']:
                self.logger.log(5, "[%s] Skipping '%s'" % (module, name))
                continue
            self.logger.debug("[%s] (%s) Setting value: %s" % (module, name, value))
            self[name] = value

        # If custom paramters were added, process unprocessed values
        for custom_parameter in custom_parameters:
            self._process_unprocessed(custom_parameter)

        # Append the module to the list of loaded modules, avoid recursion
        self['modules'].append(module)

    def validate(self) -> None:
        """ Validate config, checks that all values are processed, sets validated flag."""
        if self['_processing']:
            self.logger.critical("Unprocessed config values: %s" % ', '.join(list(self['_processing'].keys())))
        self['validated'] = True

    def __str__(self) -> str:
        return pretty_print(self.data)
