## Code style

Python code in this repository is black formatted with a line length of 120.

### Logging

Log lines info (20) level or greater should be formatted such that:

* Mentioned values of variables appear at the end of the line
* Error lines with multiple values should color and/or enclose the values in brackets to make them easier to read
* The device/volume/mountpoint where info is obtained from should be in brackets at the start of the line
* Error lines dumping config should be prefaced with a newline
* Messages adding context should be printed before any exceptions are raised
* Format strings should be used for any log line with substituted values


#### Examples

Here, the device path is enclosed in brackets (and colored blue), and the autodetected kernel module is colored magenta:
```
[/dev/sda1] Auto-enabling kernel modules for device: sd_mod
```

Here, the ignored kernel module is at the end of the line and colored red:
```
Ignored kernel modules: faux_driver
```

Here, "root" and "dm-0" are colored blue while the name of the volume "root" is colored cyan:
```
INFO     | [root] Configuring cryptsetup for LUKS mount (root) on: dm-0
root:
  key_type: gpg
  key_file: /boot/key.luks.gpg
  try_nokey: True
  key_command: gpg --decrypt /boot/key.luks.gpg
  plymouth_key_command: gpg --batch --pinentry-mode loopback --passphrase-fd 0 --decrypt /boot/key.luks.gpg
  reset_command: { gpgconf --reload && einfo "$(gpg --card-status)"; }
  uuid: 7655e3be-5b8e-4ce0-a7dd-1519b16857e6
```

### Colors

Variables should generally be colored using the following scheme:

* `cyan` for autodetected values, other than ones related to the kernel or kernel modules
* `blue` for device info, variable names, and stage info
* `green` for written/read files
* `magenta` for kernel/kmod related things
* `yellow` when cleaning files/build directories, soft warnings
* `red` for overrides or hard warnings

> colorize may be imported as c_

### Variable names

bools to disable validation should be named in the format: `no_validate_<attr>`.

> bools are initialized to `False` so do not need to be set unless defaulting to `True`

### Function names

* Variable processing functions MUST be named in the format: `_process_<attr>`.
* Functions which are not used outside of the module should be prefixed with an underscore.
* Autodetection functions should be named in the format: `autodetect_<attr>`.
* Enumeration functions should be named `get_<thing>`. such as `get_blkid_info`.
* Validation functions should be named in the format: `validate_<attr>`.
* Check functions should be named in the format: `check_<attr>`.
* Functions which move files into the build dir or image should be named `deploy_<thing>`.
* Functions which update the exports should be named `export_<thing>`. such as `export_mount_info`.

### Failure modes

When the shell script fails, it should call `rd_fail` which then calls `rd_restart`.

`rd_restart` cannot function properly in a subshell, so any functions which could possibly use it should not be called through `$()` or similar. This causes the script to fail, but continue execution after the failure.


