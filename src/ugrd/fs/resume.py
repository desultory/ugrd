__version__ = "0.2.0"


def handle_resume(self) -> None:
    """Returns a bash script handling resume from hibernation.
    Checks that /sys/power/resume is writable, and if resume= is set, if so,
    it checks ifthe specified device exists, then echo's the resume device to /sys/power/resume.
    In the event of failure, it prints an error message and a list of block devices.
    """
    return [
        'if [ -n "$(readvar resume)" ] && [ -w /sys/power/resume ]; then',
        '    if [ -e "$(readvar resume)" ]; then',
        '        einfo "Resuming from: $(readvar resume)"',
        "        readvar resume > /sys/power/resume",
        '        eerror "Failed to resume from $(readvar resume)"',
        "    else",
        '        eerror "Resume device not found: $(readvar resume)"',
        "    fi",
        r'    eerror "Block devices:\n$(blkid)"',
        '    prompt_user "Press enter to continue booting."',
        "fi",
    ]
