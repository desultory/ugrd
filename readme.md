# Initramfs generator

This project is a framework which can be used to generate an initramfs.

Executing `./main.py` will read the config from `config.toml` and use that to generate an initramfs.

The goal of the project was to design one that can be used to enter GPG keys for LUKS keyfiles over serial, to boot a btrfs raided filesystem.

## Usage

To use this script, configure `config.toml` to meet specifications and run `./main.py` as root.

> Example configs are available in the repo

### Passing a config file by name

Another config file can be used by passing it as an argument to `main.py`.

The example config can be used with `./main.py example_config.toml`

## Configuration

The main configuration file is `config.toml`

### Module config

#### base.base

`out_dir` (/tmp/initramfs) changes where the script writes the output files.

`clean` (true) forces the build dir to be cleaned on each run.

`shebang` (#!/bin/bash) sets the shebang on the init script.


##### Mounts

`mounts`: A dictionary containing entries for mounts, with their associated config.

`root_mount` a dict that acts similarly to user defined `mounts`. `destination` is hardcoded to `/mnt/root`.

The most minimal mount entry that can be created must have a name, which will be used as the `destination`, and a `source`.
If the source is a dict, options such as the `uuid`, `partuuid`, and `label` can be defined as targets, in that order.
If the source is a string, that path will be used as the mount source.

If `type` is not set, `auto` will be used for fstab entries, and for mount commands, the type will be left unspecified.

The following configuration mounts the device with `uuid` `ABCD-1234` at `/boot`:

```
[mounts.boot.source]
uuid = "ABCD-1234"
```

The following configuration mounts the device with `label` `extra` to `/mnt/extra`:

```
[mounts.extra]
destination = "/mnt/extra"

[mounts.extra.source]
label = "extra"
```

`base_mount` (false) is used for builtin mounts such as `/dev`, `/sys`, and `/proc`. Setting this to mounts it with a mount command in `init_pre` instead of waiting for `init_main`.

`skip_unmount` (false) is used for the builtin `/dev` mount, since it will fail to unmount when in use. Like the name suggests, this skips running `umount`.

`remake_mountpoint` will recreate the mountpoint with mkdir before the `mount -a` is called.

##### General mount options

These are set at the global level and are not associated with an individual mount.

`mount_wait` (false) waits for user input before attenmpting to mount the generated fstab at runtime.

`mount_timeout` timeout for `mount_wait` to automatically continue.

#### base.kmod

This module is used to embed kernel modules into the initramfs. Both parameters are optional.
If the module is loaded, but configuration options are not passed, the generator will pull all currently running kernel modules from the active kernel.

`kernel_version` (uname -r) is used to specify the kernel version to pull modules for, should be a directory under `/lib/modules/<kernel_version>`.

`kernel_modules` is used to define a list of kernel module names to pull into the initramfs. If it is not set, all loaded kernel modules will be pulled.

`kmod_ignore` is used to specify kernel modules to ignore. If a module depends on one of these, it will throw an error and drop it from being included.

`kmod_init`  is used to specify kernel modules to load at boot. If set, ONLY these modules will be loaded with modprobe. If unset, `kernel_modules` is used.

`_kmod_depend` is meant to be used within modules, specifies kernel modules which should be added to `kernel_modules` and `kmod_init`.

`kmod_ignore_softdeps` (false) ignore softdeps for kernel modules.

#### base.console

This module creates an agetty session. This is used by the `ugrd.crypto.gpg` module so the tty can be used for input and output.

`console.{name}.type` (tty) specifies the console type, such as `tty` or `vt100`.

`console.{name}.baud` specifies the baud rate if using a serial device. Required for types other than `tty`.

`consle.{name}.local` specifies whether or not the `-L` flag should be passed to agetty.


#### base.btrfs

Importing this module will run `btrfs device scan` and pull btrfs modules. No config is required.

#### base.zfs

Importing this module imports zfs userspace utils and the zfs kernel modules. The `root_mount.source.label` must be set for this to function.

This module masks the `urgd.base.base.mount_root` function from `init_mount`.

#### crypto.gpg

This module is required to perform GPG decryption within the initramfs. It depends on the `ugrd.base.console` module for agetty, which is required for input.

No configuration options are provided by this module, but it does set the `primary_console` to `tty0` and creates the console entry for it.
This configuration can be overriden in the specified user config if an actual serial interface is used, this is demonstrated in `config_raid_crypt_serial.toml`

#### crypto.smartcard

Depends on the `ugrd.crypto.gpg` submodule, meant to be used with a YubiKey.

`sc_public_key` should point to the public key associated with the smarcard used to decrypt the GPG protected LUKS keyfile.

#### crypto.cryptsetup

This module is used to decrypt LUKS volumes in the initramfs.

`cryptsetup` is a dictionary that contains the root devices to decrypt. `key_file` is optional within this dict, but `uuid` is required, ex:

```
[cryptsetup.root]
uuid = "9e04e825-7f60-4171-815a-86e01ec4c4d3"
```

`key_type` can be either `gpg` or `keyfile`. If it is not set, cryptsetup will prompt for a passphrase. If this is set globally, it applies to all `cryptsetup` definitions.

If a key is being used, it can be specified with `key_file` under the cryptsetup entry. This WILL NOT be pulled as a dependency, and is indented to be on some `mount` which is properly mounted.

### General config

The following configuration options can exist in any module, or the base config

#### binaries

All entires specified in the `binaries` list will be imported into the initramfs.

`lddtree` is used to find the required libraries.

#### paths

All entries in the `paths` list will be created as folders under the `./initramfs` directory.

They should not start with a leading `/`

### modules

The modules config directive should contain a list with names specifying the path of which will be loaded, such as `base.base`, `base.console` or `crypto.crypsetup`.

Another directory for modules can be created, the naming scheme is similar to how python imports work.

When a module is loaded, `initramfs_generator.py` will try to load a toml file for that module, parsing it in the same manner `config.yaml` is parsed.

The order in which modules/directives are loaded is very important!

If a module depends on another module, it can be added to the `mod_depends` list in the module config. A `ValueError` will be thrown if the module is not present.

### imports

The most powerful part of a module is the `imports` directive.

Imports are used to hook into the general processing scheme, and become part of the main `InitramfsGenerator` object.

Portions are loaded into the InitramfsGenerator's `config_dict` which is an `InitramfsConfigDict`

`imports` are defined like:

```
[imports.<hook>]
"module_dir.module_name" = [ "function_to_inject" ]
```

For example:

```
[imports.build_tasks]
"base.base" = [ "generate_fstab" ]
```

Is used in the base module to make the initramfs generator generate a fstab durinf the `build_tasks` phase.

Imported functions have access to the entire `self` scope, giving them full control of whatever other modules are loaded when they are executed, and the capability to dynamically create new functions.

This script should be executed as root, to have access to all files and libraries required to boot, so special care should be taken when loading and creating modules. 

#### masks

To mask an import used by another module, the mask parameter can be used:

```
[mask]
init_final = ['mount_root']

```

This will mask the `mount_root` function pulled by the base module, if another mount function is being used.

#### config_processing

These imports are very special, they can be used to change how parameters are parsed by the internal `config_dict`.

A good example of this is in `base.py`:

```
def _process_mounts_multi(self, key, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'fstab_mounts'
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
"base.base" = [ "_process_mounts_multi" ]
```

#### build_tasks

Build tasks are functions which will be executed after the directory structure has been generated using the specified `paths`.

The base module includes a build task for generating the fstab, which is activated with:

```
[imports.build_tasks]
"base.base" = [ "generate_fstab" ]
```

#### init hooks

By default, the specified init hooks are: `'init_pre', 'init_main', 'init_late', 'init_final'`

These hooks are defined under the `init_types` list in the `InitramfsGenerator` object.

When the init scripts are generated, functions under dicts in the config defined by the names in this list will be called to generate the init scripts.

This list can be updated to add or disable portions.  The order is important, as most internal hooks use `init_pre` and `init_final` to wrap every other init category, in order.

Each function should return a list of strings containing the shell lines, which will be written to the `init` file.

A general overview of the procedure used for generating the init is to write the chosen `shebang`, build in `init_pre`, then everything but `init_final`, then finally `init_final`.  These init portions are added to one file.

#### custom_init

To entirely change how the init files are generated, `custom_init` can be used. 

The `console` module uses the `custom_init` hook to change the init creation procedure.

Like with the typical flow, it starts by creating the base `init` file with the shebang and `init_pre` portions. Once this is done, execution is handed off to all fucntions present in the `custom_init` imports.

Finally, like the standard init build, the `init_final` is written to the main `init` file.

```
[imports.custom_init]
"base.console" = [ "custom_init" ]
```

The custom init works by creating an `init_main` file and returning a config line which will execute that file in a getty session.
This `init_main` file contains everything that would be in the standard init file, but without the `init_pre` and `init_final` portions. 


```
def custom_init(self):
    """
    init override
    """
    from os import chmod
    with open(f"{self.out_dir}/init_main.sh", 'w', encoding='utf-8') as main_init:
        main_init.write("#!/bin/bash\n")
        [main_init.write(f"{line}\n") for line in self.generate_init_main()]
    chmod(f"{self.out_dir}/init_main.sh", 0o755)
    return console_init(self)


def console_init(self):
    """
    start agetty
    """
    name = self.config_dict['primary_console']
    out_str = f"agetty --autologin root --login-program /init_main.sh {name}"

    console = self.config_dict['console'][name]

    if console.get('local'):
        out_str += " -L"

    console_type = console.get('type', 'tty')

    if console_type != 'tty':
        baud_rate = console['baud']
        out_str += f" {console_type} {baud_rate}"
    else:
        out_str += f" {console_type}"

    return [out_str]
```
