# Installation

To install `ugrd`, clone the repo and run `pip install .`.

> Setting `--break-system-packages` may be necessary

## Gentoo

`ugrd` is a testing package in the ::gentoo repos. It can be installed after allowing the following keywords:

```
sys-kernel/ugrd ~amd64
dev-python/zenlib ~amd64
dev-python/pycpio ~amd64
sys-kernel/installkernel ~amd64
```
Installkernel can be set to use `ugrd` by setting the following USE flags:

```
sys-kernel/installkernel -dracut ugrd
```
