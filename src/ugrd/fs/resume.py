__version__ = "0.5.0"


""" Shell lines to sanity check the environment for resuming, logs any issues """
_SANITY_CHECK_RESUME = [
    "if check_var noresume; then",  # Check if noresume= is set, if so skip resuming
    "    ewarn 'Skipping resume: noresume set'",  # If so, print
    "    return 1",  # Skip resuming
    "fi",
    # Check if /sys/power/resume is writable, if not print a message and skip resuming
    "[ -w /sys/power/resume ] || { eerror 'Skipping resume: /sys/power/resume not writable'; return 1; }",
    # Check if /sys/power/resume is not "0:0", if it is, warn that resume is being attempted again
    '[ "$(cat /sys/power/resume)" != "0:0" ] && ewarn "Resume device is not 0:0, resume may have been attempted already. Attempting to resume again..."',
]

""" Shell lines to attempt resuming from the $resume variable, logs the attempt and any failure """
_DO_RESUME = [
    'einfo "Attempting to resume from: $resume"',  # Print the resume device
    'klog "[UGRD] Attempting to resume from: $resume"',  # Log the resume device
    'printf "%s" "$resume" > /sys/power/resume',  # Attempt to resume
    'eerror "Failed to resume from: $resume"',  # If it fails, print an error message
    'klog "[UGRD] Failed to resume from: $resume"',  # Log the failure
]

""" Shell lines to get the $resume device from the resume= kernel parameter """
_GET_RESUME_DEVICE = [
    "resumeval=$(readvar resume)",  # read the cmdline resume var
    # Check if resume= is set, if not print a message and skip resuming
    '[ -n "$resumeval" ] || { ewarn "No resume device specified: resume= kernel parameter not set"; return 1; }',
    'if printf "%s" "$resumeval" | grep -q =; then',  # Check if resume= value contains an "="
    '    resume="$(blkid -t "$resumeval" -o device)"',  # Attempt to resolve the resume device using blkid
    'elif [ -e "$resumeval" ]; then',  # If it doesn't contain an "=", check if the specified resume= value is a valid path
    '    resume="$resumeval"',  # If it is, use the resume= value
    "fi",
]


_STRICT_FAIL_LINES = [
    "    if check_var ugrd_recovery; then",
    "        eerror 'If you wish to continue booting, fix the resume var or disable resuming with: setvar noresume 1'",
    "    fi",
    '    rd_fail "Cannot resume from invalid device: $resume ($resumeval)"',  # Fail with an error message
    "fi",
]

""" Shell lines to fail when strict mode is enabled """
_STRICT_CHECK_RESUME = [
    'if [ ! -b "$resume" ]; then',  # Check if the resume device is a block device
    "    eerror 'Resume device is not a block device: $resume'",
    *_STRICT_FAIL_LINES,
    'if [ -z "$resume" ]; then',  # Check if the resume device var is empty, if so print an error message and fail
    "    eerror 'Failed to resolve resume device from resume= parameter: $resumeval'",
    *_STRICT_FAIL_LINES,
]


def handle_resume(self) -> list[str]:
    """Returns a shell script handling resume from hibernation.
    Checks that /sys/power/resume is writable, resume= is set, and noresume is not set

    if "=" is in the resume= kernel parameter, it attempts to resolve the resume device using blkid -t <resume= value> -o device.

    If the specified device exists, writes resume device to /sys/power/resume.
    If strict_resume is enabled and the resume device is not a block device, stop booting and rd_fail with an error message.
    Otherwise, warn that resume failed but continue booting.

    !!!
    Resuming or failing to do so is potentially dangerous.
    If the system was hibernated, and fails to resume, it will be in an inconsistent state.
    If the system is freshly booted, it will not be able to resume, as there is no hibernation image.
    Distinguishing between a fresh boot and missing/borked hibernation image is not possible at run time.
    !!!
    """
    out_lines = []
    out_lines += _SANITY_CHECK_RESUME
    out_lines += _GET_RESUME_DEVICE
    if self["strict_resume"]:
        self.logger.info(
            "Enabling strict resume checks: invalid resume devices will cause the boot to fail instead of skipping resume"
        )
        out_lines += _STRICT_CHECK_RESUME
    else:
        out_lines += [
            '[ -n "$resume" ] || { ewarn "Failed to resolve resume device from resume= parameter: $resumeval"; return 1; }',  # If the resume device is empty, print a warning and skip resuming
        ]
    out_lines += _DO_RESUME
    if self["strict_resume"]:
        out_lines += [
            'rd_fail "Failed to resume from: $resume"',
        ]

    return out_lines
