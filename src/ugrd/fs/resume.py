__version__ = "0.5.0"


def handle_resume(self) -> list[str]:
    """Returns a shell script handling resume from hibernation.
    Checks that /sys/power/resume is writable, resume= is set, and noresume is not set

    if "=" is in the resuume= kernel parameter, it attempts to resolve the resume device using blkid -t <resume= value> -o device.

    If the specified device exists, writes resume device to /sys/power/resume.
    In the event of failure, it prints an error message, then runs rd_fail.

    !!!
    Resuming or failing to do so is potentially dangerous.
    If the system was hibernated, and fails to resume, it will be in an inconsistent state.
    If the system is freshly booted, it will not be able to resume, as there is no hibernation image.
    Distinguising between a fresh boot and missing/borked hibernation image is not possible at run time.
    !!!
    """
    return [
        "if check_var noresume; then",  # Check if noresume is set
        "    ewarn 'Skipping resume: noresume set'",  # If so, print a message and skip resuming
        "    return",  # Skip resuming
        "fi",
        # Check if /sys/power/resume is writable, if not print a message and skip resuming
        "[ -w /sys/power/resume ] || { eerror 'Skipping resume: /sys/power/resume not writable'; return 1; }",
        "resumeval=$(readvar resume)",  # read the cmdline resume var
        # Check if resume= is set, if not print a message and skip resuming
        '[ -n "$resumeval" ] || { ewarn "No resume device specified: resume= kernel parameter not set"; return 1; }',
        'if printf "%s" "$resumeval" | grep -q =; then',  # Check if resume= value contains an "="
        '    resume="$(blkid -t "$resumeval" -o device)"',  # Attempt to resolve the resume device using blkid
        "else",
        '    if [ -b "$resumeval" ]; then',  # If it doesn't contain an "=", check if it's a block device
        '        resume="$resumeval"',  # If not, use the resume= value as the
        '    else',
        '        rd_fail "resume= parameter specified but is not a block device: $resumeval"',  # If it is not, print an error message and fail
        "    fi",
        "fi",
        'if [ -z "$resume" ]; then',
        "    eerror 'Refusing to boot, resume= parameter specified but failed to resolve a device with blkid'",  # If blkid fails, print an error message
        "    if check_var ugrd_recovery; then",  # If the recovery shell is enabled, print a different message
        "        eerror 'If you wish to continue booting, fix the resume var or disable resuming with: setvar noresume 1'",  # If so, print a message about how to disable resuming from the recovery shell
        "    fi",
        '    rd_fail "Failed to resolve resume device from resume= parameter: $resumeval"',
        "fi",
        'einfo "Attempting to resume from: $resume"',  # Print the resume device
        'klog "[UGRD] Attempting to resume from: $resume"',  # Log the resume device
        'printf "%s" "$resume" > /sys/power/resume',  # Attempt to resume
        'eerror "Failed to resume from: $resume"',  # If it fails, print an error message
        'klog "[UGRD] Failed to resume from: $resume"',  # Log the failure
    ]
