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

`ugrd` is available in the AUR as [ugrd](https://aur.archlinux.org/packages/ugrd) (for the latest release version) and [ugrd-git](https://aur.archlinux.org/packages/ugrd-git) (for the latest commit). It can be installed with the usual steps for [installing and upgrading AUR packages](https://wiki.archlinux.org/title/Arch_User_Repository#Installing_and_upgrading_packages), or by using an [AUR helper](https://wiki.archlinux.org/title/AUR_helpers). For example, `yay`:

`yay ugrd`

Once installed, running `ugrd` will generate an initramfs for the latest installed kernel.