# Bootloader configuration

Once the initramfs image has been created, the system must be configured to use it. Depending on the booloader, this can be done in different ways.

## efibootmgr configuration

If the kernel is built with the `CONFIG_EFI_STUB` option, the path of the initramfs can be passed to it with the `initrd=` command line option.

This can be set with:

`efibootmgr -c -d /dev/sda -L "Gentoo UGRD" -l 'vmlinuz-gentoo.efi' -u 'initrd=ugrd.cpio'`

> This example assumes that the ESP is the first partition on `/dev/sda`, the kernel is named `vmlinuz-gentoo.efi` under the root of the ESP, and `ugrd.cpio` is also on the ESP root.

> On some systems, the EFI may remove entries that don't follow a particular format.

## Embedding the initramfs image into the kernel

The initramfs image can be embedded into the kernel image itself. This can be done by setting the `CONFIG_INITRAMFS_SOURCE` option in the kernel configuration.

The `build_dir`can be embedded into the Linux kernel with:

```
CONFIG_INITRAMFS_SOURCE="/tmp/initramfs"
```

A CPIO file can be embedded into the Linux kernel with: 

```
CONFIG_INITRAMFS_SOURCE="/usr/src/initramfs/ugrd.cpio"
```

> The CPIO must be decompressed before being embedded.

## Making the kernel automatically search for the initamfs image

To make the kernel try to load a specific initrd file at boot, without embedding it:

```
CONFIG_CMDLINE_BOOL=y
CONFIG_CMDLINE="initrd=ugrd.cpio"
```

> This will use `ugrd.cpio` under the ESP.
