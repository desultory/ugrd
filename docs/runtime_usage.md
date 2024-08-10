# Runtime usage

`ugrd` runs the `init` script generated in the build dir. In cases where `agetty` is needed, all but basic initialization and the final switch_root are performed in `init_main.sh`.

UGRD should prompt for relevant input or warn if devices are missing at runtime.

> If UGRD does not print its version after the kernel calls /init, the `ugrd.base.console` module may need to be enabled to start an agetty session.

### Failure recovery

In the event of a failure, modules will either fail through, or re-exec the init script.

The `recovery` cmdline arg will allow a shell to be spawned in the event of a failure. This is useful for debugging.
