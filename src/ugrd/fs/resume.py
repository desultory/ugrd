__version__ = "0.3.0"


def handle_resume(self) -> None:
    """Returns a bash script handling resume from hibernation.
    Checks that /sys/power/resume is writable, and if resume= is set, if so,
    it checks ifthe specified device exists, then echo's the resume device to /sys/power/resume.
    In the event of failure, it prints an error message and a list of block devices.
    """
    out_str = [
        'if [ -n "$(readvar resume)" ] && [ -w /sys/power/resume ]; then',
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
            '''    eerror " or run 'setvar resume ""' to clear the resume device."''',
            '    rd_fail "Failed to resume from $(readvar resume)."',
        ]
    else:
        out_str += ['   eerror "Failed to resume from $(readvar resume)"']

    out_str += ["fi"]

    return out_str
