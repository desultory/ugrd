# Dev manual

Modules are defined using TOML and extend the functionality of the initramfs generator.

> Modules do not need to have executable code and can serve as meta-modules referencing sets of other modules and setting config

Functionality is added by defining `imports` in modules which define functions which can modify all build/config/init generation.

> `build` functions are allowed to mutate config, init functions are not. Init is the final build task where bash files are generated.

# Configuration Architecture

All config is stored in a magic UserDict, not really but it may seem that way.

Essentially all parameters are defined in modules, with a few being built in, mostly to hold the structure for the import system and parameter registration.

Parameters defined within modules are imported after `modules` and `imports`, and the last module (highest level) setting a value will take precedence.

## Custom parameters

Parameters are defined in the `custom_parameters` dict, where the key is the name, and the value is the expected type.

The order of this dict defines the order in which enqueued values will be processed (where relevant)

### Parameter Initialization

All parameters are initialized to 'empty/zero' values, this is defined in the `_process_custom_parameters` builtin.

### Modifying parameters

Scalar values can be updated normally, but this can be changed with a  `custom_processing` function.

Iterables such as dicts and lists are automatically appended/updated unless a `custom_processing` function is associated with that parameter.

### late_args

Parameters defined in `_late_args` will only be loaded just before the build phase (after all defined modules are loaded).

This can be used to ensure parameters with dynamic processors can change functionality based on config which may be defined in other modules.

A key example is the `no_kmod` parameter which could interfere with a `kernel_version` being set by tooling such as installkernel on a system where no kernel modules are needed.

Another example is the `binaries` parameter which may need to be short circuited for certain utilities if busybox is used.

# Modules

All µgRD components take the form of modules. Modules consist of a TOML definition which may `import` code from a python file.

`_module_name` can be set within a module for logging purposes, it is verified to be accurate when imported but optional.

## Imports

µgRD allows python functions to be imported from modules using the `imports` dict.

`imports` entries have a key which is the name of the hook to import into, and a value which is a dict of module names and lists of functions to import.

For example, to import function `get_foo` into runlevel `bar` from module `baz`:

```
[imports.bar]
"baz" = ["get_foo"]
```

### Import hooks (types)

There are two primary categories for imports, `build` and `init`.

`build` imports are used to mutate the config and build the base structure of the initramfs.

`init` imports are used to generate the init scripts.

For config which requires special validation or handling, `config_processing` hooks can be made to process parameters as soon as they are set.

The `pack`, `checks`, and `test` hooks should be self explanatory and are explained below.

#### Build imports

Build imports are used to mutate config and build the base structure of the initramfs.

The following hooks are used internally and are defined in `InitramfsGenerator.build_tasks`:

* `build_enum` - Used for system enumeration, such as finding the root device, loaded kernel mods, etc.
* `build_pre` - For build tasks run at the very start of the build, such as directory cleaning and possibly late enumeration/config processing.
* `build_tasks` - Functions which will be executed after `build_pre`, which make up the majority of the build process.
* `build_deploy` Where components are actually copied/created in the build directory.
* `build_final` The last  default build hook, where finalizing tasks such as image metadata regeneration take place.

## Init imports

By default, the following init hooks are available:

* `init_pre` - Where the base initramfs environment is set up; basic mounts are initialized and the kernel cmdline is read.
* `init_debug` - Where a shell is started if `start_shell` is enabled in the debug module.
* `init_main` - Most important initramfs activities should take place here.
* `init_mount` - Where the root filesystem mount takes place
* `init_final` - Where `switch_root` is executed.

> These hooks are defined under the `init_types` list in the `InitramfsGenerator` object.

When the init scripts are generated, functions under dictionaries in the config defined by the names in this list will be called to generate the init scripts.

Init functions should return a string or list of strings that contain shell lines to be added to the `init` file.

The `InitramfsGenerator.generate_init_main()` function (often called from `self`) can be used to output all init hook levels but `init_pre` and `init_final`.

A general overview of the procedure used for generating the init is to write the chosen `shebang`, then every init hook. The `custom_init` import can be used for more advanced configurations, such as running another script in `agetty`.

### custom_init

To change how everything but `init_pre` and `init_file` are handled at runtime, `custom_init` can be used.

The `console` module uses the `custom_init` hook to change the init creation procedure.

Like with the typical flow, it starts by creating the base `init` file with the shebang and `init_pre` portions. Once this is done, execution is handed off to all functions present in the `custom_init` imports.

Finally, like the standard init build, the `init_final` is written to the main `init` file.

```
[imports.custom_init]
"ugrd.base.console" = [ "custom_init" ]
```

The `custom_init` function should return a tuple with the line used to call the custom init file, and the contents of it.


```
def custom_init(self) -> str:
    """
    init override for the console module.
    Write the main init runlevels to self._custom_init_file.
    Returns the output of console_init which is the command to start agetty.
    """
    custom_init_contents = [self['shebang'],
                            f"# Console module version v{__version__}",
                            *self.generate_init_main()]

    return console_init(self), custom_init_contents


def console_init(self) -> str:
    """
    Start agetty on the primary console.
    Tell it to execute teh _custom_init_file
    If the console is a serial port, set the baud rate.
    """
    name = self['primary_console']
    console = self['console'][name]

    out_str = f"agetty --autologin root --login-program {self['_custom_init_file']}"

    console_type = console.get('type', 'tty')

    if console_type != 'tty':
        # This differs from usage in the man page but seems to work?
        out_str += f" --local-line {console['baud']}"

    out_str += f" {name} {console_type}"

    return out_str
```

### Config processing

`config_processing` imports are used to automatically process config values when they are modified at runtime.

While defined similarly to other imports, they are not associated with any runlevel and run whenever the associated parameter is modified.

This can be used to validate config values, or to automatically process them.

> Functions added to `config_processing` should be named in the format `_process_<varname>{,_multi}` where _multi is added to run values through @handle_plural

A good example of this is in `base.py`:

```
def _process_mounts_multi(self, key, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'mounts'
    """
    if 'destination' not in mount_config:
        mount_config['destination'] = f"/{key}"  # prepend a slash

    try:
        self['mounts'][key] = FstabMount(**mount_config)
        self['paths'].append(mount_config['destination'])
    except ValueError as e:
        self.logger.error("Unable to process mount: %s" % key)
        self.logger.error(e)
```

This module manages mount management, and loads new mounts into fstab objects, also defined in the base module.

A new root variable named `foo` could be defined, and a function `_process_foo` could be created and imported, raising an error when this value is found, for example.

This module is loaded in the imports section of the `base.toml` file:

```
[imports.config_processing]
"ugrd.fs.mounts" = [ "_process_mounts_multi" ]
```

### Pack

The `pack` import is primarily used for packing the CPIO archive.

The `cpio` module imports the `make_cpio_list` packing function with:

```
[imports.pack]
"ugrd.fs.cpio" = [ "make_cpio" ]
```

### Checks

The `checks` import is used for static checks, such as ensuring required files are included in the CPIO and have reasonable contents.

### Test

The `test` import is used for testing the initramfs, and is mostly used by the `test` module for QEMU wrapping.

## Importing functions

Functions are imported from modules by specifying the hook they are to be added to in the `imports` dict, with the module name as the key and a list of functions to import as the value.

For example, the `generate_fstab` function is added to the `build_tasks` book from the `ugrd.fs.mounts` module with:

```
[imports.build_tasks]
"ugrd.fs.mounts" = [ "generate_fstab" ]
```

## Import order

Imports can be ordered using the `import_order` dict.

The key name defined in `before` will be run before values in the `after` list (value) by name.

Likewise, keys in the `after` list will be run after the key in the `before` value.

> `after` targets are moved before the key when creating the hook order, not literally after.

For example, to run function "foo" before function "bar":

```
[import_order.before]
"foo" = "bar"
```

To run function "baz" after "foo" and "bar":

```
[import_order.after]
"baz" = ["foo", "bar"]
```

## Provides/needs

Modules can provide/need a certain "tag" to be set by other modules.

Provided tags are stored in config["provided"], which is a set of strings, each tag must be unique and cannot be provided by multiple modules.

If a module has a `provides` string or list of strings, those will be added to config["provided"].
When a module has a `needs` string or list of strings, those will be checked against config["provided"].

Needed tags are checked after module imports and before any module config. Provided tags are set upon successful module import.

# Example module

The following is an example module which prints "hello world" during the init process:
```
# /var/lib/ugrd/hello_world.py

def hello_world(self) -> str:
    """
    Print hello world to the console
    """
    return "echo 'Hello world!'"

```

```
# /var/lib/ugrd/hello_world.toml

[imports.init_main]
"hello_world" = [ "hello_world" ]

```

This module can be used with `ugrd -m hello_world`

