__version__ = "0.3.1"


def handle_resume(self) -> None:
    """Returns a bash script handling resume from hibernation.
    Checks that /sys/power/resume is writable, resume= is set, and noresume is not set, if so,
    it checks ifthe specified device exists, then echo's the resume device to /sys/power/resume.
    In the event of failure, it prints an error message and a list of block devices.
    """
    out_str = [
        'if ! check_var noresume && [ -n "$(readvar resume)" ] && [ -w /sys/power/resume ]; then',
        '    if [ -e "$(readvar resume)" ]; then',
        '        einfo "Resuming from: $(readvar resume)"',
        "        readvar resume > /sys/power/resume",
        '        eerror "Failed to resume from $(readvar resume)"',
        '        eerror "Resume device not found: $(readvar resume)"',
        "    fi",
        r'    eerror "Block devices:\n$(blkid)"',
    ]
    if self["safe_resume"]:
        out_str += [
            '    eerror "If you wish to continue booting, remove the resume= kernel parameter."',
            '''    eerror " or run 'setvar noresume 1' to skip resuming."''',
            '    rd_fail "Failed to resume from $(readvar resume)."',
        ]
    else:
        out_str += ['   eerror "Failed to resume from $(readvar resume)"']

    out_str += ["fi"]

    return out_str
