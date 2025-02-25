__author__ = "desultory"
__version__ = "2.3.4"

from collections import UserDict
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from queue import Queue
from tomllib import TOMLDecodeError, load
from typing import Callable

from pycpio import PyCPIO
from zenlib.logging import loggify
from zenlib.types import NoDupFlatList
from zenlib.util import colorize, handle_plural, pretty_print


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

    builtin_parameters = {
        "modules": NoDupFlatList,  # A list of the names of modules which have been loaded, mostly used for dependency checking
        "provided": NoDupFlatList,  # A list of tags provided by modules
        "imports": dict,  # A dict of functions to be imported into the initramfs, under their respective hooks
        "import_order": dict,  # A dict containing order requirements for imports
        "validated": bool,  # A flag to indicate if the config has been validated, mostly used for log levels
        "custom_parameters": dict,  # Custom parameters loaded from imports
        "custom_processing": dict,  # Custom processing functions which will be run to validate and process parameters
        "_processing": dict,
    }  # A dict of queues containing parameters which have been set before the type was known

    def __init__(self, NO_BASE=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Define the default parameters
        for parameter, default_type in self.builtin_parameters.items():
            if default_type == NoDupFlatList:
                self.data[parameter] = default_type(no_warn=True, _log_bump=5, logger=self.logger)
            else:
                self.data[parameter] = default_type()
        self["import_order"] = {"before": {}, "after": {}}
        if not NO_BASE:
            self["modules"] = "ugrd.base.base"
        else:
            self["modules"] = "ugrd.base.core"

    def import_args(self, args: dict, quiet=False) -> None:
        """Imports data from an argument dict."""
        log_level = 10 if quiet else 20
        for arg, value in args.items():
            self.logger.log(log_level, f"[{colorize(arg, 'blue')}] Setting from arguments: {colorize(value, 'green')}")

            if arg == "modules":  # allow loading modules by name from the command line
                for module in value.split(","):
                    self[arg] = module
            elif getattr(self, arg, None) != value:  # Only set the value if it differs:
                self[arg] = value
            else:
                self.logger.debug("Skipping unchanged argument '%s' with value: %s" % (arg, value))

    def __setitem__(self, key: str, value) -> None:
        if self["validated"]:
            return self.logger.error(
                "[%s] Config is validated, refusing to set value: %s" % (key, colorize(value, "red"))
            )
        # If the type is registered, use the appropriate update function
        if any(key in d for d in (self.builtin_parameters, self["custom_parameters"])):
            return self.handle_parameter(key, value)
        else:
            self.logger.debug(
                "[%s] Unable to determine expected type, valid builtin types: %s"
                % (key, self.builtin_parameters.keys())
            )
            self.logger.debug("[%s] Custom types: %s" % (key, self["custom_parameters"].keys()))
            # for anything but the logger, add to the processing queue
            if key != "logger":
                self.logger.debug("Adding unknown internal parameter to processing queue: %s" % key)
                if key not in self["_processing"]:
                    self["_processing"][key] = Queue()
                self["_processing"][key].put(value)

    def handle_parameter(self, key: str, value) -> None:
        """
        Handles a config parameter, setting the value and processing it if the type is known.
        Raises a KeyError if the parameter is not registered.

        Uses custom processing functions if they are defined, otherwise uses the standard setters.
        """
        # Get the expected type, first searching builtin_parameters, then custom_parameters
        for d in (self.builtin_parameters, self["custom_parameters"]):
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
            """Checks if the funnction is masked."""
            return import_name in self.get("masks", [])

        if func := self["custom_processing"].get(f"_process_{key}"):
            if check_mask(func.__name__):
                self.logger.debug("Skipping masked function: %s" % func.__name__)
            else:
                self.logger.log(5, "[%s] Using custom setitem: %s" % (key, func.__name__))
                return func(self, value)

        if func := self["custom_processing"].get(f"_process_{key}_multi"):
            if check_mask(func.__name__):
                self.logger.debug("Skipping masked function: %s" % func.__name__)
            else:
                self.logger.log(5, "[%s] Using custom plural setitem: %s" % (key, func.__name__))
                return handle_plural(func)(self, value)

        if expected_type in (list, NoDupFlatList):  # Append to lists, don't replace
            self.logger.log(5, "Using list setitem for: %s" % key)
            return self[key].append(value)

        if expected_type is dict:  # Create new keys, update existing
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
        if isinstance(parameter_type, str):
            parameter_type = eval(parameter_type)

        self["custom_parameters"][parameter_name] = parameter_type
        self.logger.debug("Registered custom parameter '%s' with type: %s" % (parameter_name, parameter_type))

        match parameter_type.__name__:
            case "NoDupFlatList":
                self.data[parameter_name] = NoDupFlatList(no_warn=True, _log_bump=5, logger=self.logger)
            case "list" | "dict":
                self.data[parameter_name] = parameter_type()
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
                self.data[parameter_name] = PyCPIO(logger=self.logger, _log_bump=10)
            case _:  # For strings and things, don't init them so they are None
                self.logger.warning("Leaving '%s' as None" % parameter_name)
                self.data[parameter_name] = None

    def _process_unprocessed(self, parameter_name: str) -> None:
        """Processes queued values for a parameter."""
        if parameter_name not in self["_processing"]:
            self.logger.log(5, "No queued values for: %s" % parameter_name)
            return

        value_queue = self["_processing"].pop(parameter_name)
        while not value_queue.empty():
            value = value_queue.get()
            if self["validated"]:  # Log at info level if the config has been validated
                self.logger.info("[%s] Processing queued value: %s" % (parameter_name, value))
            else:
                self.logger.debug("[%s] Processing queued value: %s" % (parameter_name, value))
            self[parameter_name] = value

    def _process_import_order(self, import_order: dict) -> None:
        """Processes the import order, setting the order requirements for import functions.
        Ensures the order type is valid (before, after),
        that the function is not ordered after itself.
        Ensures that the same function/target is not in another order type.
        """
        self.logger.debug("Processing import order:\n%s" % pretty_print(import_order))
        order_types = ["before", "after"]
        for order_type, order_dict in import_order.items():
            if order_type not in order_types:
                raise ValueError("Invalid import order type: %s" % order_type)
            for function in order_dict:
                targets = order_dict[function]
                if not isinstance(targets, list):
                    targets = [targets]
                if function in targets:
                    raise ValueError("Function cannot be ordered after itself: %s" % function)
                for other_target in [self["import_order"].get(ot, {}) for ot in order_types if ot != order_type]:
                    if function in other_target and any(target in other_target[function] for target in targets):
                        raise ValueError("Function cannot be ordered in multiple types: %s" % function)
                order_dict[function] = targets

            if order_type not in self["import_order"]:
                self["import_order"][order_type] = {}
            self["import_order"][order_type].update(order_dict)

        self.logger.debug("Registered import order requirements: %s" % import_order)

    def _process_import_functions(self, module, functions: list) -> list[Callable]:
        """Processes defined import functions, importing them and adding them to the returned list.
        the 'function' key is required if dicts are used,
        'before' and 'after' keys can be used to specify order requirements."""
        function_list = []
        for f in functions:
            match type(f).__name__:
                case "str":
                    function_list.append(getattr(module, f))
                case "dict":
                    if "function" not in f:
                        raise ValueError("Function key not found in import dict: %s" % functions)
                    func = f["function"]
                    function_list.append(getattr(module, func))
                    if "before" in f:
                        self["import_order"] = {"before": {func: f["before"]}}
                    if "after" in f:
                        self["import_order"] = {"after": {func: f["after"]}}
                case _:
                    raise ValueError("Invalid type for import function: %s" % type(f))
        return function_list

    @handle_plural
    def _process_imports(self, import_type: str, import_value: dict) -> None:
        """Processes imports in a module, importing the functions and adding them to the appropriate list."""
        for module_name, function_names in import_value.items():
            self.logger.debug("[%s]<%s> Importing module functions : %s" % (module_name, import_type, function_names))
            try:  # First, the module must be imported, so its functions can be accessed
                module = import_module(module_name)
            except ModuleNotFoundError as e:
                module_path = Path("/var/lib/ugrd/" + module_name.replace(".", "/")).with_suffix(".py")
                self.logger.debug("Attempting to sideload module from: %s" % module_path)
                if not module_path.exists():
                    raise ModuleNotFoundError("Module not found: %s" % module_name) from e
                try:  # If the module is not built in, try to lade it from /var/lib/ugrd
                    spec = spec_from_file_location(module_name, module_path)
                    module = module_from_spec(spec)
                    spec.loader.exec_module(module)
                except Exception as e:
                    raise ModuleNotFoundError("Unable to load module: %s" % module_name) from e

            self.logger.log(5, "[%s] Imported module contents: %s" % (module_name, dir(module)))
            if "_module_name" in dir(module) and module._module_name != module_name:
                self.logger.warning("Module name mismatch: %s != %s" % (module._module_name, module_name))

            if import_type not in self["imports"]:  # Import types are only actually created when needed
                self.logger.log(5, "Creating import type: %s" % import_type)
                self["imports"][import_type] = NoDupFlatList(_log_bump=10, logger=self.logger)

            if import_masks := self.get("masks", {}).get(import_type, {}).get(module_name):
                import_masks = [import_masks] if isinstance(import_masks, str) else import_masks
                for mask in import_masks:
                    if mask in function_names:
                        self.logger.warning("[%s] Skipping import of masked function: %s" % (module_name, mask))
                        function_names.remove(mask)
                        if import_type == "custom_init":
                            self.logger.warning("Skipping custom init function: %s" % mask)
                            continue

            function_list = self._process_import_functions(module, function_names)
            if not function_list:
                self.logger.warning("[%s] No functions found for import: %s" % (module_name, import_type))
                continue

            if import_type == "custom_init":  # Only get the first function for custom init (should be 1)
                if isinstance(function_list, list):
                    custom_init = function_list[0]
                else:
                    custom_init = function_list

                if self["imports"]["custom_init"]:
                    self.logger.warning("Custom init function already defined: %s" % self["imports"]["custom_init"])
                else:
                    self["imports"]["custom_init"] = custom_init
                    self.logger.info(
                        "Registered custom init function: %s" % colorize(custom_init.__name__, "blue", bold=True)
                    )
                    continue

            if import_type == "funcs":  # Check for collisions with defined binaries and functions
                for function in function_list:
                    if function.__name__ in self["imports"]["funcs"]:
                        raise ValueError("Function '%s' already registered" % function.__name__)
                    if function.__name__ in self["binaries"]:
                        raise ValueError("Function collides with defined binary: %s'" % function.__name__)

            # Append the functions to the appropriate list
            self["imports"][import_type] += function_list
            self.logger.debug("[%s] Updated import functions: %s" % (import_type, function_list))

            if import_type == "config_processing":  # Register the functions for processing after all imports are done
                for function in function_list:
                    self["custom_processing"][function.__name__] = function
                    self.logger.debug("Registered config processing function: %s" % function.__name__)
                    self._process_unprocessed(
                        function.__name__.removeprefix("_process_")
                    )  # Re-process any queued values

    @handle_plural
    def _process_modules(self, module: str) -> None:
        """processes a single module into the config"""
        if module in self["modules"]:
            self.logger.debug("Module '%s' already loaded" % module)
            return

        self.logger.info("Processing module: %s" % colorize(module, bold=True))

        module_subpath = module.replace(".", "/") + ".toml"

        module_path = Path(__file__).parent.parent / module_subpath
        if not module_path.exists():
            module_path = Path("/var/lib/ugrd") / module_subpath
            if not module_path.exists():
                raise FileNotFoundError("Unable to locate module: %s" % module)
        self.logger.debug("Module path: %s" % module_path)

        with open(module_path, "rb") as module_file:
            try:
                module_config = load(module_file)
            except TOMLDecodeError as e:
                raise TOMLDecodeError("Unable to load module config: %s" % module) from e

        if imports := module_config.get("imports"):
            self.logger.debug("[%s] Processing imports: %s" % (module, imports))
            self["imports"] = imports

        if needs := module_config.get("needs"):
            if isinstance(needs, str):
                if needs not in self["provided"]:
                    raise ValueError("[%s] Required tag not provided: %s" % (module, needs))
            elif isinstance(needs, list):
                for need in needs:
                    if need not in self["provided"]:
                        raise ValueError("[%s] Required tag not provided: %s" % (module, need))
            else:
                raise ValueError("[%s] Invalid needs value: %s" % (module, needs))

        custom_parameters = module_config.get("custom_parameters", {})
        if custom_parameters:
            self.logger.debug("[%s] Processing custom parameters: %s" % (module, custom_parameters))
            self["custom_parameters"] = custom_parameters

        for name, value in module_config.items():  # Process config values, in order they are defined
            if name in ["imports", "custom_parameters", "provides", "needs"]:
                self.logger.log(5, "[%s] Skipping '%s'" % (module, name))
                continue
            self.logger.debug("[%s] (%s) Setting value: %s" % (module, name, value))
            self[name] = value

        # If custom paramters were added, process unprocessed values
        for custom_parameter in custom_parameters:
            self._process_unprocessed(custom_parameter)

        # Append the module to the list of loaded modules, avoid recursion
        self["modules"].append(module)

        if provides := module_config.get("provides"):  # Handle provided tags last
            self.logger.debug("[%s] Provided: %s" % (module, provides))
            self["provided"] = provides

    def validate(self) -> None:
        """Validate config, checks that all values are processed, sets validated flag."""
        if self["_processing"]:
            self.logger.critical(
                "Unprocessed config values: %s"
                % colorize(", ".join(list(self["_processing"].keys())), "red", bold=True)
            )
        self["validated"] = True

    def __str__(self) -> str:
        return pretty_print(self.data)
