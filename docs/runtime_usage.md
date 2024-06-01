## Runtime usage

`ugrd` runs the `init` script generated in the build dir with `bash -l` by default.

Required functions are sourced from `/etc/profile`.

Unless `quiet` is passed as a kernel parameter, UGRD will print information as it initialized.

In cases where user input is required, a magenta prompt will be displayed.

### custom_init

When a `custom_init` is being used, the majority of the initialization process is handled within that custom script, and it will be exited in the event of a failure.

### Failure recovery

If the `recovery` kernel parameter is passed, UGRD will drop to a shell when there is a failure.

This shell can be used to debug issues, or manually setup mounts and rewrite config vars.

Once required changes have been made, the `exit` command will continue the boot process.

