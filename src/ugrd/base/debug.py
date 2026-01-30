__author__ = "desultory"
__version__ = "1.5.0"

from os import environ
from pathlib import Path

from ugrd.exceptions import AutodetectError, ValidationError
from zenlib.util import colorize, contains, unset

EXPECTED_EDITORS = {"nano", "vim", "vi"}
# removed emacs, it doesn't work without lots of scripts and info from /usr/share, hard to keep the image a reasonable size


@unset("editor")
def autodetect_editor(self):
    """ Auto-detect the editor from the environment. """
    self["editor"] = environ.get("EDITOR", "nano")

def _process_editor(self, editor: str):
    """ Process the editor configuration. """
    _validate_editor(self, editor)

    try:  # setting value will automatically call the hook to validate the path/deps
        self["binaries"] = editor
    except AutodetectError:
        # reraise to specifically flag editor config
        raise AutodetectError("Failed to locate editor binary and dependencies: %s" % colorize(editor, "red"))
    self.logger.info("[debug] Using editor: %s" % colorize(editor, "cyan"))
    self.data["editor"] = editor

def _validate_editor(self, editor: str):
    """ Checks that the configured editor has been tested and is known to work. """
    editor_name = Path(editor).name  # validate the basename of the editor, in case full path is specified
    if editor_name not in EXPECTED_EDITORS:
        if self["validate"] and not self["no_validate_editor"]:
            raise ValidationError("Unrecognized editor: %s" % colorize(editor_name, "red"))
        else:
            self.logger.warning("Configured editor is not recognized: %s" % colorize(editor_name, "yellow"))
            self.logger.warning("If this is intentional, set 'no_validate_editor' to suppress this warning.")


def start_shell(self) -> str:
    """Start a shell at the start of the initramfs."""
    outstr ="""
    if ! check_var ugrd_debug; then
        ewarn "The ugrd.base.debug module is enabled, but ugrd_debug is not enabled!"
        return
    fi
    einfo "Starting debug shell"
    """
    if self["debug_tty2"]:
        outstr += 'einfo "Starting debug shell on tty2"\n'
        outstr += "setsid -c sh -i </dev/tty2 >/dev/tty2 2>/dev/tty2 &\n"
        outstr += "wait_for_space\n"
    else:
        outstr += "setsid -c sh -i -l\n"

    return outstr


@contains("start_shell", "Not enabling the debug shell, as the start_shell option is not set.", log_level=30)
def enable_debug(self) -> str:
    """Enable debug mode."""
    return "setvar ugrd_debug 1"
