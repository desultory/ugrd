# Dev manual

Modules can be created to extend the functionality of the initramfs generator.

Modules only require a toml definition, and can import other modules to act as meta-modules.

Python functions can be added imported into `init` and `build` runlevels to execute build tasks or output init lines.

> `build` functions are allowed to mutate config, init functions are not. Init is the final build task where bash files are generated.

Within modules, all config values are imported, then processed according to the order of the `custom_parameters` list.

`_module_name` can be set within a module for logging purposes, it is verified to be accurate when imported but optional.

## Imports

UGRD allows python functions to be imported from modules using the `imports` dict.

`imports` entries have a key which is the name of the hook to import into, and a value which is a dict of module names and lists of functions to import.

### Import types

There are two primary categories for imports, `build` and `init`. Build imports are used to mutate the config and build the base structure of the initramfs, while init imports are used to generate the init scripts.

`config_processing` imports are used to automatically process config values when they are modified at runtime.

The `pack` import is primarly used for packing the CPIO archive.

The `checks` import is used for static checks, such as ensuring required files are included in the CPIO and have reasonbale contents.

The `test` import is used for testing the initramfs, and is mostly used by the `test` module for QEMU wrapping.

### Importing functions

Functions are imported from modules by specifying the hook they are to be added to in the `imports` dict, with the module name as the key and a list of functions to import as the value.

For example, the `generate_fstab` function is added to the `build_tasks` book from the `ugrd.fs.mounts` module with:

```
[imports.build_tasks]
"ugrd.fs.mounts" = [ "generate_fstab" ]
```

## Build imports

Build imports are used to mutate config and build the base structure of the initramfs.

### build_pre

`build_pre` contains build tasks which are run at the very start of the build, such as build directory cleaning and additional config processing.

### build_tasks

`build_tasks` are functions which will be executed after `build_pre`, which make up the majority of the build process.

### build_late

`build_late` are finalizing build functions, immediately before files are deployed

### build_deploy

`build_deploy` is mostly for builtin functions and is where components are actually copied into the build directory.

### build_final

`build_final` is the last build hook, where finalizing tasks take place.

## Init imports

By default, the following init hooks are available:
* `init_pre` - Where the base initramfs environment is set up; basic mounts are initialized and the kernel cmdline is read.
* `init_debug` - Where a shell is started if `start_shell` is enabled in the debug module.
* `init_early` - Where early actions such as checking for device paths, mounting the fstab take place.
* `init_main` - Most important initramfs activities should take place here.
* `init_late` - Space for late initramfs actions, such as activating LVM volumes.
* `init_premount` - Where filesystem related commands such as `btrfs device scan` can run.
* `init_mount` - Where the root filesystem mount takes place
* `init_mount_late` - Where late mount actions such as mounting paths under the root filesystem can take place.
* `init_cleanup` - Currently unused, where cleanup before `switch_root` should take place.
* `init_final` - Where `switch_root` is executed.

> These hooks are defined under the `init_types` list in the `InitramfsGenerator` object.

When the init scripts are generated, functions under dicts in the config defined by the names in this list will be called to generate the init scripts.

Init functions should return a string or list of strings that contain shell lines to be added to the `init` file.

The `InitramfsGenerator.generate_init_main()` function (often called from `self`) can be used to output all init hook levels but `init_pre` and `init_final`.

A general overview of the procedure used for generating the init is to write the chosen `shebang`, then every init hook. The `custom_init` import can be used for more advanced confugrations, such as running another script in `agetty`.

### custom_init

To change how everything but `init_pre` and `init_file` are handled at runtime, `custom_init` can be used.

The `console` module uses the `custom_init` hook to change the init creation procedure.

Like with the typical flow, it starts by creating the base `init` file with the shebang and `init_pre` portions. Once this is done, execution is handed off to all fucntions present in the `custom_init` imports.

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

## pack

Packing functions, such as CPIO generation can be defined in the `pack` import.

The `cpio` module imports the `make_cpio_list` packing function with:

```
[imports.pack]
"ugrd.fs.cpio" = [ "make_cpio" ]
```
## Config processing

`config_processing` imports are different from typical imports. They are configured similarly, with a dict of module names and functions to import.

Instead of running once at a particular build level, `config_processing` functions are run whenever a config value is modified at runtime.

This can be used to validate config values, or to automatically process them.

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

The name of `config_prcessing` functions is very important, it must be formatted like `_process_{name}` where the name is the root variable name in the yaml config.

If the function name has `_multi` at the end, it will be called using the `handle_plural` function, iterating over passed lists/dicts automatically.

A new root varaible named `oops` could be defined, and a function `_process_oops` could be created and imported, raising an error when this vlaue is found, for example.

This module is loaded in the imports section of the `base.yaml` file:

```
[imports.config_processing]
"ugrd.fs.mounts" = [ "_process_mounts_multi" ]
```

