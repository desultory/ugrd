# Initramfs generator

This project is a framework which can be used to generate an initramfs.

Executing `python ./main.py` will read the config from `config.yaml` and use that to generate an initramfs.

The goal of the project was to design one that can be used to enter GPG keys for LUKS keyfiles over serial, to boot a btrfs raided filesystem.


## Connfiguration

The main configuration file is `config.yaml`

### binaries

All entires specified in the `binaries` list will be imported into the initramfs.

`lddtree` is used to find the required libraries.


### paths

All entries in the `paths` list will be created as folders under the `./initramfs` directory.

They should not start with a leading /


### Modules

This file contains a list of modules which will be loaded, such as `base`, `serial` or `crypsetup`.

When a module is loaded, `initramfs_generator.py` will try to load that yaml file, parsing it in the same manner `config.yaml` is parsed.

The order in which modules/directives are loaded is very important!

All of the config could be placed in a single file, but it makes more sense to organize it.


### Imports

The most powerful part of a module is the imports.

Imports are used to hook into the general processing scheme, and become part of the main `InitramfsGenerator` object.


#### config_processing

These imports are very special, they can be used to change how parameters are parsed.

A good example of this is in `base.py`:

```
def _process_mounts(self, key, mount_config):
    """
    Processes the passed mounts into fstab mount objects
    under 'fstab_mounts'
    """
    self['mounts'][key] = FstabMount(destination=f"/{key}", **mount_config)

```

This module manages mount management, and loads new mounts into fstab objects, also defined in the base module.

The name of it is important, it must be formatted like `_process_{name}` where the name is the root variable name in the yaml config.

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

When the init scripts are generated, functions in these lists (in the config) will be called to generate the init scripts.

Each function should return a list of strings containing the shell lines.

The general procedure for generating the init is to write the chosen `shebang`, build in `init_pre`, then everything but `init_final`, then finally `init_final`.  These init portions are added to one file.

#### custom_init

To entirely change how the init files are generated, `custom_init` can be used. 

The `serial` module uses the `custom_init` hook to change the init creation procedure.

Like with the typical flow, it starts by creating the base `init` file with the shebang and `init_pre` portions. Once this is done, execution is handed off to all fucntions present in the `custom_init` imports.

Finally, like the standard init build, the `init_final` is written to the main `init` file.


