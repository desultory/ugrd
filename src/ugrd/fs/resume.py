__version__ = "0.4.2"

from zenlib.util import contains, unset

def _resume(self) -> None:
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
        "resumeval=$(readvar resume)",  # read the cmdline resume var
        'if ! check_var noresume && [ -n "$resumeval" ] && [ -w /sys/power/resume ]; then',
        '    if echo "$resumeval" | grep -q -E "^PARTUUID=|^UUID="; then',  # resolve partuuid to device
        '        resume=$(blkid -t "$resumeval" -o device)',
        "    else",
        "        resume=$resumeval",
        "    fi",
        '    if [ -e "$resume" ]; then',  # Check if the resume device exists
        '        einfo "Resuming from: $resume"',
        '        printf "%s" "$resume" > /sys/power/resume',  # Attempt to resume
        '        ewarn "Failed to resume from: $resume"',
        "    else",
        '        ewarn "Resume device not found: $resume)"',  # Warn if the resume device does not exist
        r'        eerror "Block devices:\n$(blkid)"',
        '        eerror "If you wish to continue booting, remove the resume= kernel parameter."',
        '''        eerror " or run 'setvar noresume 1' from the recovery shell to skip resuming."''',
        '        rd_fail "Failed to resume from $(readvar resume)."',
        "    fi",
        "fi",
    ]

@unset('late_resume')
def handle_resume(self) -> None:
    return _resume(self)

@contains('late_resume')
def handle_late_resume(self) -> None:
    self.logger.warning("WARNING: Late resume enabled, can cause instability if not used with caution. Highly recommended to read configuration documentation before use.")
    return _resume(self)
