# Usage

Once installed, `ugrd` can be executed as root to create an initramfs based on the definition in `/etc/ugrd/config.toml`.

## Supplying configuration

Alternate configuration can be supplied with:

`ugrd -c example_config.toml`

## Overriding the output location

The last argument is the output file, which can be a path:

`ugrd /boot/ugrd.cpio`

> If no path information is supplied, the filename provided will be created under `build_dir`

## Hostonly mode

The `hostonly` boolean is enabled by default and is required for `validation`.

`hostonly` mode is also required for most runtime config autodetection, since it's read from the build host.

It can be forced at runtime with `--hostonly` and disabled with `--no-hostonly`.

## Validation mode

The `validate` option is set by default and attempts to verify that the generated initramfs will work on the system creating it.

It can be forced at runtime with `--validate` and disabled with `--no-validate`.

## Build logging

Verbose information about what what is being moved into the initramfs build directory can be enabled by setting `build_logging` to `true`.

`_build_log_level` can be manually set to any log level. It is incremented by 10 when `build_logging` is enabled, with a minimum of 20.

This can be enabled at runtime with `--build-logging` or disabled with `--no-build-logging`

The output can be logged to a file instead of stdout by specifying a log file with `--log-file`

# Output

An initramfs environment will be generated at `build_dir` (`/tmp/initramfs/`).

The initramfs will be packed to `out_dir` (`/tmp/initramfs_out`) and named `out_file` (`ugrd.cpio`).

# Image configuration/information

The final config dict can be printed with `--print-config`.

A list of functions by runlevel can be printed with `--print-init`.
