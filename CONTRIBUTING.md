## Code style

Python code in this repository is black formatted with a line length of 120.

### Logging

Log lines info (20) level or greater should be formatted such that:

* Mentioned values of variables appear at the end of the line
* The device/volume/mountpoint where info is obtained from should be in brackets at the start of the line

### Colors

Variables should generally be colored using the following scheme:

* `cyan` for autodetected values
* `green` for written files
* `magenta` for kernel/kmod related things
* `yellow` when cleaning files/build directories
* `red` for overrides or warnings

### Variable names

bools to disable validation should be named in the format: `no_validate_<attr>`.

> bools are initialized to `False` so does not need to be set unless defaulting to `True`

### Function names

* Variable processing functions MUST be named in the format: `_process_<attr>`.
* Functions which are not used outside of the module should be prefixed with an underscore.
* Autodetection functions should be named in the format: `autodetect_<attr>`.
* Validation functions should be named in the format: `validate_<attr>`.
* Functions which move files into the build dir or image should be named `deploy_<thing>`.
* Functions which update the exports should be named `export_<thing>`. such as `export_mount_info`.
* Enumeration functions should be named `get_<thing>`. such as `get_blkid_info`.