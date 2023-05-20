# Initramfs generator

This project is a framework which can be used to generate an initramfs.

Executing `./main.py` will read the config from `config.yaml` and use that to generate an initramfs.

The goal of the project was to design one that can be used to enter GPG keys for LUKS keyfiles over serial, to boot a btrfs raided filesystem.

## Usage

To use this script, configure `config.yaml` to meet specifications and run `./main.py` as root.

Another config file can be used by passing it as an argument to `main.py`.

The example config can be used with `./main.py example_config.yaml`

## Configuration

The main configuration file is `config.yaml`

### General config

#### out_dir

Setting `out_dir` changes where the script writes the output files, it defaults to `initramfs` in the local dir.

#### clean

Setting `clean` to `true` makes the script clean the output directory prior to generating it.


### binaries

All entires specified in the `binaries` list will be imported into the initramfs.

`lddtree` is used to find the required libraries.


### paths

All entries in the `paths` list will be created as folders under the `./initramfs` directory.

They should not start with a leading `/`


### modules

The modules config directive should contain a list with names specifying the path of which will be loaded, such as `base_modules.base`, `base_modules.serial` or `base_modules.crypsetup`.

Another directory for modules can be created, the naming scheme is similar to how python imports work.

When a module is loaded, `initramfs_generator.py` will try to load that yaml file, parsing it in the same manner `config.yaml` is parsed.

The order in which modules/directives are loaded is very important!

All of the config could be placed in a single file, but it makes more sense to organize it.


### imports

The most powerful part of a module is the `imports` directive.

Imports are used to hook into the general processing scheme, and become part of the main `InitramfsGenerator` object.

Portions are loaded into the InitramfsGenerator's `config_dict` which is an `InitramfsConfigDict`

`imports` are defined with the first key being the nameof the import type, the value being the path of the python module to be imported, which has a list containing functions to be imported, in order.

Imported functions have access to the entire `self` scope, giving them full control of whatever other modules are loaded when they are executed, and the capability to dynamically create new functions.

This script should be executed as root, to have access to all files and libraries required to boot, so special care should be taken when loading and creating modules. 

#### config_processing

These imports are very special, they can be used to change how parameters are parsed by the internal `config_dict`.

A good example of this is in `base.py`:

```
def _process_mounts_multi(self, key, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'fstab_mounts'
    """
    self['mounts'][key] = FstabMount(destination=f"/{key}", **mount_config)

```

This module manages mount management, and loads new mounts into fstab objects, also defined in the base module.

The name of `config_prcessing` functions is very important, it must be formatted like `_process_{name}` where the name is the root variable name in the yaml config.

If the function name has `_mulit` at the end, it will be called using the `handle_plural` function, iterating over passed lists/dicts automatically.

A new root varaible named `oops` could be defined, and a function `_process_oops` could be created and imported, raising an error when this vlaue is found, for example.

This module is loaded in the imports section of the `base.yaml` file:

```
mports:
  config_processing:
    base:
      - _process_mounts
  build_tasks:
    base:
      - generate_fstab
  init_pre:
    base:
      - mount_fstab
  init_late:
    base:
      - mount_root
  init_final:
    base:
      - clean_mounts
      - switch_root

```

#### build_tasks

Build tasks are functions which will be executed after the directory structure has been generated using the specified `paths`.

The `base` module contains one for generating the fstab using mounts loaded into the `FstabMount` objects.

#### init_hook

By default, the specified init hooks are: `'init_pre', 'init_main', 'init_late', 'init_final'`

These hooks are defined under the `init_types` list in the `InitramfsGenerator` object.

When the init scripts are generated, functions under dicts in the config defined by the names in this list will be called to generate the init scripts.

This list can be updated to add or disable portions.  The order is important, as most internal hooks use `init_pre` and `init_final` to wrap every other init category, in order.

Each function should return a list of strings containing the shell lines, which will be written to the `init` file.

A general overview of the procedure used for generating the init is to write the chosen `shebang`, build in `init_pre`, then everything but `init_final`, then finally `init_final`.  These init portions are added to one file.

#### custom_init

To entirely change how the init files are generated, `custom_init` can be used. 

The `serial` module uses the `custom_init` hook to change the init creation procedure.

Like with the typical flow, it starts by creating the base `init` file with the shebang and `init_pre` portions. Once this is done, execution is handed off to all fucntions present in the `custom_init` imports.

Finally, like the standard init build, the `init_final` is written to the main `init` file.

```
imports:
  custom_init:
    serial:
      - custom_init


```

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
    return serial_init(self)


def serial_init(self):
    """
    start agetty
    """
    try:
        out = list()
        for name, config in self.config_dict['serial'].items():
            if config.get('local'):
                out.append(f"agetty --autologin root --login-program /init_main.sh -L {config['baud']} {name} {config['type']}")
            else:
                out.append(f"agetty --autologin root --login-program /init_main.sh {config['baud']} {name} {config['type']}")
        return out

```

This function creates a new `init_main.sh` file which contains everything but the `init_pre` and `init_final` bits, and returns the ouput of the `serial_init` function which references that new `init_main.sh` file.

The end result is the init script starting a shell in the location specified using the `serial` config dict which calls and runs the main portion of the init.
