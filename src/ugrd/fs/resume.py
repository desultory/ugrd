__version__ = "0.1.0"

def handle_resume(self) -> None:
    """Returns a bash script handling resume if specified.
    Checks that /sys/power/resume is writable, and if resume= is set, if so,
    it checks ifthe specified device exists, then echo's the resume device to /sys/power/resume."""
    return [
        'if [ -n "$(readvar resume)" ] && [ -w /sys/power/resume ]; then',
        '    if [ -e "$(readvar resume)" ]; then',
        '        einfo "Resuming from: $(readvar resume)"',
        "        readvar resume > /sys/power/resume",
        '        rd_fail "Failed to resume from $(readvar resume)"',
        "    else",
        '        ewarn "Resume device not found: $(readvar resume)"',
        '        prompt_user "Press enter to continue booting."',
        "    fi",
        "fi",
    ]
