__version__ = "0.4.2"

from zenlib.util import contains


def resume(self) -> None:
    """Returns a shell script handling resume from hibernation.
    Checks that /sys/power/resume is writable, resume= is set, and noresume is not set, if so,
    checks if UUID= or PARTUUID= or LABEL= is in the resume var,
    and tries to use blkid to find the resume device.
    If the specified device exists, writes resume device to /sys/power/resume.
    In the event of failure, it prints an error message, a list of block devuices, then runs rd_fail.


    Resuming or failing to do so is potentially dangerous.
    If the system was hibernated, and fails to resume, it will be in an inconsistent state.
    If the system is freshly booted, it will not be able to resume, as there is no hibernation image.
    Distinguising between a fresh boot and missing/borked hibernation image is not possible at run time.
    """
    return [
        # Check resume support
        '[ -n "$1" ] || (ewarn "No device?" ; return 1)',
        '[ -w /sys/power/resume ] || (ewarn "Kernel does not support resume!" ; return 1)',
        '[[ ! "$(cat /sys/power/resume)" == "0:0" ]] || ewarn "/sys/power/resume not empty, resume has already been attempted!"',
        # Safety checks
        "if ! [ -z $(lsblk -Q MOUNTPOINT)] ; then",
        r'    eerror "Cannot safely resume with mounted block devices:\n$(lsblk -Q MOUNTPOINT -no PATH)"',
        "    return 1",
        "fi",
        '[ -b "$1" ] || (ewarn "\'$1\' is not a valid block device!" ; return 1)',
        'einfo "Attempting resume from: $1"',
        'echo -n "$1" > /sys/power/resume',
        'einfo "No image on $resume"',
        "return 0",
    ]


def handle_early_resume(self) -> None:
    return [
        "resumeval=$(readvar resume)",  # read the cmdline resume var
        'if ! check_var noresume && [ -n "$resumeval" ] && [ -w /sys/power/resume ]; then',
        '    if echo "$resumeval" | grep -q "UUID="     ||',      #    resolve uuid to device
        '       echo "$resumeval" | grep -q "PARTUUID=" ||',      # or resolve partuuid to device
        '       echo "$resumeval" | grep -q "LABEL="    ; then',  # or resolve label to device
        '        resume=$(blkid -t "$resumeval" -o device)',
        "    else",
        '        resume="$resumeval"',
        "    fi",
        "    if ! [ -z $resume ] ; then",
        '        if ! resume "$resume" ; then',
        '            eerror "If you wish to continue booting, remove the resume= kernel parameter."',
        '''             eerror " or run 'setvar noresume 1' from the recovery shell to skip resuming."''',
        '            rd_fail "Failed to resume from $(readvar resume)."',
        "        fi",
        "    else",
        "        einfo \"Resume device '$resumeval' not found\"",
        "    fi",
        "fi",
    ]


@contains("late_resume")
def handle_late_resume(self) -> None:
    self.logger.warning(
        "[late_resume] enabled, this can result in data loss if filesystems are modified before resuming. Read the docs for more info."
    )
    return handle_early_resume(
        self
    )  # At the moment it's the same code but delayed, will change when more features are added


@contains("test_resume")
def test_init_swap_uuid(self):
    if "test_cpu" in self:
        from uuid import uuid4

        self["test_swap_uuid"] = swap_uuid = uuid4()

        # append to test kernel cmdline and adjust planned image size to allow enough space
        self["test_cmdline"] = f"{self.get('test_cmdline')} resume=UUID={swap_uuid}"
        self["test_image_size"] = 256 + self.get("test_image_size")
