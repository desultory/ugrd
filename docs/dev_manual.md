# Dev manual

Modules can be created to extend the functionality of the initramfs generator.

Modules only require a toml definition, and can import other modules to act as meta-modules.

Python functions can be added imported into `init` and `build` runlevels to execute build tasks or output init lines.

## Imports

UGRD allows python functions to be imported from modules using the `imports` dict.

There are two primary categories for imports, `build` and `init`.

`pack` and `test` imports can also be used, but are mostly reserved for image packing and testing.

### Build imports

Build imports are used to mutate config and build the base structure of the initramfs.

##### build_pre

`build_pre` contains build tasks which are run at the very start of the build, such as build directory cleaning and additional config processing.

##### build_tasks

`build_tasks` are functions which will be executed after `build_pre`, such as dependency pulling.

##### build_late

`build_late` functions are executed after the init has been generated.

### init hooks

By default, the specified init hooks are:
* `init_pre` - Where the base initramfs environment is set up, such as creating a devtmpfs.
* `init_debug` - Where a shell is started if `start_shell` is enabled in the debug module.
* `init_early` - Where early actions such as checking for device paths, mounting the fstab take place.
* `init_main` - Most important initramfs activities should take place here.
* `init_late` - Space for additional checks, stuff that should run later in the init process.
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

#### custom_init

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

### pack

Packing functions, such as CPIO generation can be defined in the `pack` import.

The `cpio` module imports the `make_cpio_list` packing function with:

```
[imports.pack]
"ugrd.fs.cpio" = [ "make_cpio" ]
```

