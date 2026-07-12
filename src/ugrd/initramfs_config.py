__author__ = "desultory"
__version__ = "3.0.0"

from collections import UserDict
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from queue import Queue
from typing import Any

from pycpio import PyCPIO
from zenlib.logging import LoggerMixIn
from zenlib.types import NoDupFlatList
from zenlib.util import colorize as c_
from zenlib.util import handle_plural, parse_toml, pretty_print

from .config_helpers import DEFAULT_CONFIG_PATH, read_ugrd_module
from .exceptions import ValidationError


class InitramfsConfig(LoggerMixIn, UserDict):
    """
    Dict for ugrd config

    IMPORTANT!!!:
        This dict does not act like a normal dict, setitem is designed to append when the overrides are used
        Default parameters are defined in builtin_parameters

    By default ugrd.base.base is loaded, which is a very minimal config.
    If NO_BASE is set to True, ugrd.base.core is loaded instead, which contains absolute essentials.

    If parameters which are not registered are set, they are added to the processing queue and processed when the type is known.
    """

    builtin_parameters = {
        "modules": NoDupFlatList,  # A list of the names of modules which have been loaded, mostly used for dependency checking
        "provided": NoDupFlatList,  # A list of tags provided by modules
        "imports": dict,  # A dict of functions to be imported into the initramfs, under their respective hooks
        "import_order": dict,  # A dict containing order requirements for imports
        "validated": bool,  # A flag to indicate if the config has been validated, mostly used for log levels
        "custom_parameters": dict,  # Custom parameters loaded from imports
        "custom_processing": dict,  # Custom processing functions which will be run to validate and process parameters
        "_processing": dict,  # A dict of queues containing parameters which have been set before the type was known
        "_late_args": NoDupFlatList,  # A list of arguments which could be passed as command line args but need to be processed after the config is loaded
        "stage": str,  # The current processing stage (early, late, final)
        "test_copy_config": NoDupFlatList,  # A list of config values which are copied into test images, from the parent
    }

    def __init__(
        self,
        startup_args: dict | None = None,
        config_file: Path | str | None = None,
        NO_BASE: bool = False,
        *args,
        **kwargs,
    ) -> None:
        """Initialize the initramfs config

        First, init the logger and UserDict superclass
        Then, define all default parameters

        With those defined, the base config can be loaded.
        As config modules are loaded, parameters which are not built in are queued for later processing
        The last queued value will take precedence

        The order is: base config -> user config -> arguments
        """
        self.init_logger(args, kwargs)
        super().__init__(*args, **kwargs)

        # Define the default parameters
        for parameter, default_type in self.builtin_parameters.items():
            if default_type == NoDupFlatList:
                self.data[parameter] = default_type(no_warn=True, _log_bump=5, logger=self.logger)
            else:
                self.data[parameter] = default_type()
        self["stage"] = "early"
        self["import_order"] = {"before": {}, "after": {}}

        if not NO_BASE:
            self["modules"] = "ugrd.base.base"
        else:
            self["modules"] = "ugrd.base.core"

        # If config is defined, load everything but the modules defined in it
        if config_file:
            try:
                self._load_module(parse_toml(config_file))
            except FileNotFoundError as e:
                if str(config_file) == DEFAULT_CONFIG_PATH:
                    self.logger.warning(
                        f"Using base config because default config not found: {c_(config_file, 'yellow')}"
                    )
                else:
                    raise e
        else:
            self.logger.info("No config file specified, using the base config.")

        # Import args last so they take precedence over other config
        if startup_args:
            self.import_args(startup_args)

    def import_args(self, args: dict) -> None:
        """Imports data from an argument dict."""
        for arg, value in args.items():
            self.logger.info(f"[{c_(arg, 'blue')}] Setting from arguments: {c_(value, 'blue', bold=True)}")

            if arg == "modules":  # allow loading modules by name from the command line
                for module in value.split(","):
                    self[arg] = module
            else:
                self[arg] = value

    def _enqueue(self, key: str, value: Any) -> None:
        """Adds a value to the processing queue"""
        if key not in self["_processing"]:
            self["_processing"][key] = Queue()
        self["_processing"][key].put(value)
        self.logger.debug(
            f"[{c_(key, 'blue', background=True)}] Adding parameter to processing queue: {c_(value, 'yellow')}"
        )

    def __setitem__(self, key: str, value) -> None:
        """Custom setitem for the config dict
        If the dict is validated, refuse to set config
        If it's the final stage and it's not validated, raise a critical warning

        If a _late_arg is being set and it's not in the late stage, also add it to the queue

        For registered config values, use the handle_parameter function

        For everything but the logger, queue values if they are not registered
        """
        if self["validated"]:
            return self.logger.error(
                f"[{c_(key, 'yellow')}] Config is validated, refusing to set value: {c_(value, 'red')}"
            )
        if self["stage"] == "final" and not self["validated"]:
            return self.logger.critical(
                f"[{c_(key, 'yellow')}] Config is finalized but invalid, refusing to set value: {c_(value, 'red')}"
            )

        if not self._check_late(key):
            return self._enqueue(key, value)

        # If the type is registered, use the appropriate update function
        if any(key in d for d in (self.builtin_parameters, self["custom_parameters"])):
            return self.handle_parameter(key, value)

        self.logger.log(
            5,
            f"[{c_(key, 'yellow')}] Unable to determine expected type, valid builtin types:\n{c_(self.builtin_parameters.keys(), 'blue', bold=True)}",
        )
        self.logger.log(5, f"[{c_(key, 'blue')}] Custom types: {c_(self['custom_parameters'].keys(), bold=True)}")
        # for anything but the logger, add to the processing queue
        if key != "logger":
            self._enqueue(key, value)

    def handle_parameter(self, key: str, value) -> None:
        """
        Handles a config parameter, setting the value and processing it if the type is known.
        Raises a KeyError if the parameter is not registered.

        If the value is a _late_arg, and it's not in the late stage, skip it

        Uses custom processing functions if they are defined, otherwise uses the standard setters.
        """
        # Get the expected type, first searching builtin_parameters, then custom_parameters
        for d in (self.builtin_parameters, self["custom_parameters"]):
            expected_type = d.get(key)
            if expected_type:
                if expected_type.__name__ == "InitramfsGenerator":
                    self.data[key] = value
                    return self.logger.debug(f"Setting InitramfsGenerator: {c_(key, 'magenta', bold=True)}")
                break  # Break and raise an exception if the type is not found
        else:
            raise KeyError(f"Parameter not registered: {c_(key, 'red')}")

        if hasattr(self, f"_process_{key}"):  # The builtin function is decorated and can handle plural
            self.logger.log(5, f"[{c_(key, 'blue')}] Using builtin setitem: _process_{key}")
            return getattr(self, f"_process_{key}")(value)

        # Don't use masked processing functions for custom values, fall back to standard setters
        def check_mask(import_name: str) -> bool:
            """Checks if the function is masked."""
            return import_name in self.get("masks", [])

        if func := self["custom_processing"].get(f"_process_{key}"):
            if check_mask(func.__name__):
                self.logger.debug(f"Skipping masked function: {c_(func.__name__, 'yellow', background=True)}")
            else:
                self.logger.log(
                    5, f"[{c_(key, 'blue')}] Using custom setitem: {c_(func.__name__, 'blue', underline=True)}"
                )
                return func(self, value)

        if func := self["custom_processing"].get(f"_process_{key}_multi"):
            if check_mask(func.__name__):
                self.logger.debug(f"Skipping masked function: {c_(func.__name__, 'yellow', background=True)}")
            else:
                self.logger.log(
                    5,
                    f"[{c_(key, 'blue')}] Using custom plural setitem: {c_(func.__name__, 'blue', underline=True, bold=True)}",
                )
                return handle_plural(func)(self, value)

        if expected_type in (list, NoDupFlatList):  # Append to lists, don't replace
            self.logger.log(5, f"[{c_(key, 'blue')}] Using list setitem")
            return self[key].append(value)

        if expected_type is dict:  # Create new keys, update existing
            if key not in self:
                self.logger.log(5, f"[{c_(key, 'blue')}] Setting dict to: {value}")
                return super().__setitem__(key, value)
            self.logger.log(5, f"[{c_(key, 'blue')}] Updating dict with: {value}")
            return self[key].update(value)

        casted_value = expected_type(value)
        self.logger.debug(
            f"[{c_(key, 'blue')}]{c_(expected_type, 'red', dim=True)} Setting value: {c_(casted_value, bold=True)}"
        )
        self.data[key] = casted_value  # For everything else, simply set it

    @handle_plural
    def _process_custom_parameters(self, parameter_name: str, parameter_type: type) -> None:
        """
        Updates the custom_parameters attribute.
        Sets the initial value of the parameter based on the type.

        Processes any queued values if they exist (unless they are _late_args and it is not the late stage)
        """
        if isinstance(parameter_type, str):
            parameter_type = eval(parameter_type)

        self["custom_parameters"][parameter_name] = parameter_type
        self.logger.debug(
            f"[{c_(parameter_name, 'blue')}] Registered custom parameter with type: {c_(parameter_type, 'red', dim=True)}"
        )

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
                self.logger.warning(
                    f"[{c_(parameter_name, 'blue')}] Leaving unknown parameter type as None! <{c_(parameter_type.__name__, 'red')}>"
                )
                self.data[parameter_name] = None

        # Process queued values if they exist
        self._process_unprocessed(parameter_name)

    def _process_unprocessed(self, parameter_name: str) -> None:
        """Processes queued values for a parameter.
        Does nothing if there are no queued values

        If the value is a _late_arg and it's not the late stage, skip
            this leaves the processing queue untouched
        """
        if parameter_name not in self["_processing"]:
            self.logger.log(5, f"No queued values for: {c_(parameter_name, 'yellow', dim=True)}")
            return

        if not self._check_late(parameter_name):
            return

        value_queue = self["_processing"].pop(parameter_name)
        while not value_queue.empty():
            value = value_queue.get()
            self.logger.debug(
                f"[{c_(parameter_name, 'blue')}] Processing queued value: {c_(value, 'yellow', bold=True)}"
            )
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

    def _import_external_module(self, module_name: str):
        """Given a module name, attempts to load it from /var/lib/ugrd, returning the module"""
        module_path = Path("/var/lib/ugrd/" + module_name.replace(".", "/")).with_suffix(".py")
        self.logger.debug(f"Attempting to sideload module from: {c_(module_path, 'green')}")
        if not module_path.exists():
            raise ModuleNotFoundError(f"Module not found: {c_(module_name, 'red')}")

        try:  # If the module is not built in, try to load it from /var/lib/ugrd
            # Extra checks are added for logging but mostly to make type checking happy
            spec = spec_from_file_location(module_name, module_path)
            if spec is None:
                raise ModuleNotFoundError(
                    f"[{c_(module_name, 'yellow')}] Failed to load spec from file: {c_(module_path, 'red')}"
                )

            spec_loader = spec.loader
            if spec_loader is None:
                raise RuntimeError(f"Failed to initialize loader for spec: {c_(spec, 'yellow')}")

            module = module_from_spec(spec)

            if module is None:
                raise ModuleNotFoundError(
                    f"[{c_(module_name, 'yellow')}] Failed to load module from spec: {c_(spec, 'red')}"
                )

            spec_loader.exec_module(module)
            self.logger.debug(f"Loaded external module: {c_(module_name, 'blue')}")

        except Exception as e:
            raise ModuleNotFoundError(f"[{c_(module_name, 'yellow')}] Unable to load module: {e}") from e

        self.logger.info(f"Sideloaded module: {c_(module_name, 'green')}")
        return module

    @handle_plural
    def _process_imports(self, import_type: str, import_value: dict) -> None:
        """Processes imports in a module, importing the functions and adding them to the appropriate list."""
        for module_name, function_names in import_value.items():
            f_name = f"[{c_(module_name, 'green')}]({c_(import_type, underline=True)})"
            self.logger.debug(f"{f_name} Importing module functions: {function_names}")
            try:  # First, the module must be imported, so its functions can be accessed
                module = import_module(module_name)
            except ModuleNotFoundError:  # If it can't be natively imported, try to sideload it
                module = self._import_external_module(module_name)

            self.logger.log(5, f"{f_name} Imported module contents:{dir(module)}")
            if "_module_name" in dir(module) and module._module_name != module_name:
                self.logger.warning(
                    f"Module name mismatch: {c_(module._module_name, 'green')} != {c_(module_name, 'red')}"
                )

            if import_type not in self["imports"]:  # Import types are only actually created when needed
                self.logger.log(5, f"Creating import type: {c_(import_type, underline=True)}")
                self["imports"][import_type] = NoDupFlatList(_log_bump=10, logger=self.logger)

            if import_masks := self.get("masks", {}).get(import_type, []):
                import_masks = [import_masks] if isinstance(import_masks, str) else import_masks
                for mask in import_masks:
                    if mask in function_names:
                        self.logger.warning(
                            f"[{c_(module_name, bright=True)}] Skipping import of masked function: {c_(mask, 'yellow')}"
                        )
                        function_names.remove(mask)
                        if import_type == "custom_init":
                            self.logger.warning(f"Skipping masked custom init function: {c_(mask, 'yellow')}")
                            continue

            try:
                function_list = [getattr(module, func) for func in function_names]
            except AttributeError as e:
                raise AttributeError(
                    f"[{c_(module_name, 'yellow')}] Failed to import function: {c_(e.name, 'red')}"
                ) from e

            if not function_list:
                self.logger.warning(
                    f"[{c_(module_name, 'yellow')}] No functions found for import: {c_(import_type, 'red')}"
                )
                continue

            if import_type == "custom_init":  # Only get the first function for custom init (should be 1)
                if isinstance(function_list, list):
                    custom_init = function_list[0]
                else:
                    custom_init = function_list

                if self["imports"]["custom_init"]:
                    self.logger.warning(
                        f"Custom init function already defined: {c_(self['imports']['custom_init'], 'yellow')}"
                    )
                else:
                    self["imports"]["custom_init"] = custom_init
                    self.logger.info(
                        f"[{c_(module_name, 'green')}] Registered custom init function: {c_(custom_init.__name__, 'blue', bold=True)}"
                    )
                    continue

            if import_type == "funcs":  # Check for collisions with defined binaries and functions
                for function in function_list:
                    if function.__name__ in self["imports"]["funcs"]:
                        raise ValueError(f"Function already registered: {c_(function.__name__, 'red')}")
                    if function.__name__ in self["binaries"]:
                        raise ValueError(f"Function collides with defined binary: {c_(function.__name__, 'red')}")

            # Append the functions to the appropriate list
            self["imports"][import_type] += function_list
            self.logger.log(5, f"[{c_(import_type, underline=True)}] Updated import functions: {function_list}")

            if import_type == "config_processing":  # Register the functions for processing after all imports are done
                for function in function_list:
                    self["custom_processing"][function.__name__] = function
                    self.logger.debug(f"Registered config processing function: {c_(function.__name__, 'blue')}")

    @handle_plural
    def _process_modules(self, module: str) -> None:
        """processes a single module (by name) into the config
        If that module (by name) has already been loaded, does nothing
        """
        if module in self["modules"]:
            self.logger.debug(f"Module already loaded: {c_(module, 'yellow')}")
            return

        self._load_module(read_ugrd_module(module), module)

    def _load_module(self, module_config: dict[str, Any], module: str = "config") -> None:
        """Loads a module given a config dict module_config
        the module var is used for logging and tracking loaded modules

        'imports' are registered first as they may have processing functions
        Checks needs before processing the module further

        Adds unregistered values to the processing queue if they are not lists/dicts

        Finally, registers custom values so queued values can be processed and registers provided tags if present
        """
        self.logger.info(f"Processing module: {c_(module, 'green', bold=True)}")

        if imports := module_config.get("imports"):
            self.logger.debug(f"[{c_(module, 'green')}] Processing imports: {imports}")
            self["imports"] = imports

        if needs := module_config.get("needs"):
            if isinstance(needs, str):
                if needs not in self["provided"]:
                    raise ValueError(f"[{c_(module, 'green')}] Required tag not provided: {c_(needs, 'red')}")
            elif isinstance(needs, list):
                for need in needs:
                    if need not in self["provided"]:
                        raise ValueError(f"[{c_(module, 'green')}] Required tag not provided: {c_(need, 'red')}")
            else:
                raise ValueError(f"[{c_(module, 'green')}] Invalid needs value: {c_(needs, 'red')}")

        # Process other config such as import orders, defined values
        for name, value in module_config.items():
            if name in ["imports", "custom_parameters", "provides", "needs"]:
                self.logger.log(5, f"[{c_(module, 'green')}] Skipping: {c_(name, 'yellow')}")
                continue

            self.logger.log(5, f"[{c_(module, 'green')}]({c_(name, 'blue')}) Setting value: {c_(value, bold=True)}")
            self[name] = value

        # If custom parameters are defined, process them and then process any unprocessed values
        if custom_parameters := module_config.get("custom_parameters", {}):
            self.logger.debug(f"[{c_(module, 'green')}] Processing custom parameters: {custom_parameters}")
            self["custom_parameters"] = custom_parameters

        # Append the module to the list of loaded modules, avoid recursion
        # Do not do this for modules called the default name 'config'
        if module != "config":
            self["modules"].append(module)

        # Handle provides tags, ensure only a single module provides a tag
        if provides := module_config.get("provides"):
            self.logger.debug(f"[{c_(module, bright=True)}] Processing provided tags: {c_(provides, 'green')}")
            if isinstance(provides, str):
                provides = [provides]
            for tag in provides:
                if tag in self["provided"]:
                    raise ValidationError(f"[{c_(module, 'yellow')}] Provided tag already registered: {c_(tag, 'red')}")
                self["provided"] = tag
                self.logger.info(f"[{c_(module, bright=True)}] Registered provided tag: {c_(tag, 'green', bold=True)}")

    def _check_late(self, parameter_name: str) -> bool:
        """Checks if it is time to run a late arg"""
        if self["stage"] != "late" and parameter_name in self["_late_args"]:
            self.logger.debug(
                f"[{c_(self['stage'], underline=True)}] Deferring processing for late arg: {c_(parameter_name, 'yellow')}"
            )
            return False
        return True

    def _process_late_values(self) -> None:
        """Processes all late values"""
        if self["stage"] != "late":
            raise RuntimeError(
                f"Cannot process late values in current stage: {c_(self['stage'], 'red', underline=True)}"
            )

        for arg in self["_late_args"]:
            self._process_unprocessed(arg)

    def _process_stage(self, stage: str) -> None:
        """Sets the stage
        When the stage is changed to final, calls validation and does not allow it to be changed again
        """
        if self["stage"] == "final":
            raise RuntimeError("Cannot change stage after finalized")

        self.data["stage"] = stage
        self.logger.debug(f"Entering config stage: {c_(stage, 'blue', underline=True, bold=True)}")

        if stage == "late":
            self._process_late_values()
        elif stage == "final":
            self._validate()

    def _validate(self) -> None:
        """Validate config, checks that all values are processed, sets validated flag."""
        if self["_processing"]:
            unprocessed_values = ", ".join(list(self["_processing"].keys()))
            if self["validate"]:
                raise ValidationError(
                    f"Failed to validate config. Unprocessed values: {c_(unprocessed_values, 'red', bold=True)}"
                )
            return self.logger.critical(f"Unprocessed config values: {c_(unprocessed_values, 'red', bold=True)}")
        self.data["validated"] = True

    def __str__(self) -> str:
        return pretty_print(self.data)
