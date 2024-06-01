## Usage

Once installed, `ugrd` can be executed as root to create an initramfs based on the definition in `/etc/ugrd/config.toml`.

### Supplying configuration

Alternate configuration can be supplied with:

`ugrd -c example_config.toml`

### Overriding the output location

The last argument is the output file, which can be a path:

`ugrd /boot/ugrd.cpio`

> If no path information is supplied, the filename provided will be created under `build_dir`

### Hostonly mode

The `hostonly` boolean is enabled by default and is required for `validation`.

`hostonly` mode is also required for most runtime config autodetection, since it's read from the build host.

It can be forced at runtime with `--hostonly` and disabled with `--no-hostonly`.

### Validation mode

The `validate` option is set by default and attempts to verify that the generated initramfs will work on the system creating it.

It can be forced at runtime with `--validate` and disabled with `--no-validate`.

## Output

An initramfs environment will be generated at `build_dir` (`/tmp/initramfs/`).

The initramfs will be packed to `out_dir` (`/tmp/initramfs_out`) and named `out_file` (`ugrd.cpio`).

## Config information

The final config dict can be printed with `--print-config`.

A list of functions by runlevel can be printed with `--print-init`.

### Embedding the initramfs image into the kernel

The `build_dir`can be embedded into the Linux kernel with:

```
CONFIG_INITRAMFS_SOURCE="/tmp/initramfs"
```

A CPIO file can be embedded into the Linux kernel with: 

```
CONFIG_INITRAMFS_SOURCE="/usr/src/initramfs/ugrd.cpio"
```

### Making the kernel automatically search for the initamfs image

To make the kernel try to load a specific initrd file at boot, without embedding it:

```
CONFIG_CMDLINE_BOOL=y
CONFIG_CMDLINE="initrd=ugrd.cpio"
```

> This will use `ugrd.cpio` under the ESP.

### efibootmgr configuration

If the kernel is built with the `CONFIG_EFI_STUB` option, the path of the initramfs can be passed to it with the `initrd=` command line option.

This can be set with:

`efibootmgr -c -d /dev/sda -L "Gentoo UGRD" -l 'vmlinuz-gentoo.efi' -u 'initrd=ugrd.cpio'`

> This example assumes that the ESP is the first partition on `/dev/sda`, the kernel is named `vmlinuz-gentoo.efi` under the root of the ESP, and `ugrd.cpio` is also on the ESP root.

> On some systems, the EFI may remove entries that don't follow a particular format.

### Bootloader configuration

If a CPIO file is generated, it can be passed to the bootloader. Embedding the initramfs into the kernel is preferred, as the entire kernel image can be signed.
