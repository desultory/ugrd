__author__ = "desultory"
__version__ = "1.3.1"

from zenlib.util import contains

def _determine_editor(self) -> None:
    # expected values, others raise a warning but still work fine
    expected_editors = [ 'vim', 'nano', 'emacs' ]
    
    from os import environ
    editor = self.get("editor") or environ.get("EDITOR") or "nano"
    
    # setting value will automatically call the hook to validate the path
    # reraising to tell the user it's the editor config to help narrow down the issue
    try:
        self["binaries"] = editor
    except (ValueError, RuntimeError):
        raise ValueError(f"Editor binary '{editor}' could not be located in PATH")
    
    # Report which binary gets used (send a warning if it's not recognised
    self.logger.info(f"[debug] Using '{editor}' as editor.")
    
    if editor not in expected_editors:
       self.logger.warn("Editor binary not recognised, can be overridden with 'editor' in config or EDITOR in environment if incorrect, otherwise can be disregarded.")


def start_shell(self) -> str:
    """Start a bash shell at the start of the initramfs."""
    return [
        "if ! check_var debug; then",
        '    ewarn "The debug module is enabled, but debug is not set enabled"',
        "    return",
        "fi",
        'einfo "Starting debug shell"',
        "bash -l",
    ]


@contains("start_shell", "Not enabling the debug shell, as the start_shell option is not set.", log_level=30)
def enable_debug(self) -> str:
    """Enable debug mode."""
    return "setvar debug 1"
