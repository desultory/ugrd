# Installation

To install `ugrd`, clone the repo and run `pip install .`.

> Setting `--break-system-packages` may be necessary

## Gentoo

`sys-kernel/installkernel` has a `ugrd` USE flag, when enabled, installkernel will pull ugrd and use it to generate a new initramfs on kernel installs.

The following USE flag configuration will enable `ugrd` for `installkernel`:

```
sys-kernel/installkernel ugrd
```


`ugrd` is in the ::gentoo repos. It can be installed manually with:

`emerge sys-kernel/ugrd`

## Arch Linux

`ugrd` is available in the AUR as `python-ugrd-git`. It can be installed with:

`yay ugrd`

Once installed, running `ugrd` will generate an initramfs for the latest installed kernel.

