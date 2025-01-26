__author__ = "desultory"
__version__ = "3.1.0"


def parse_cmdline_bool(self) -> str:
    """Returns a shell script to parse a boolean value from /proc/cmdline
    The only argument is the name of the variable to be read/set
    """
    return r"""
    edebug "Parsing cmdline bool: $1"
    setvar "$1" "$(grep -qE "(^|\s)$1(\s|$)" /proc/cmdline && echo 1 || echo 0)"
    """


def parse_cmdline_str(self) -> str:
    """Returns a shell script to parse a string value from /proc/cmdline
    The only argument is the name of the variable to be read/set
    """
    return r"""
    edebug "Parsing cmdline string: $1"
    val=$(grep -oP "(?<=$1=)[^\s]+" /proc/cmdline)
    if [ -n "$val" ]; then
        edebug "Parsed $1: $val"
        setvar "$1" "$val"
    fi
    """


def parse_cmdline(self) -> str:
    """Returns shell script to parse /proc/cmdline"""
    return rf"""
    cmdline=$(awk -F '--' '{{print $1}}' /proc/cmdline)  # Get everything before '--'
    setvar INIT_ARGS "$(awk -F '--' '{{print $2}}' /proc/cmdline)"  # Get everything after '--'
    for bool in {" ".join([f'"{bool}"' for bool in self["cmdline_bools"]])}; do
        parse_cmdline_bool "$bool"
    done
    for string in {" ".join([f'"{string}"' for string in self["cmdline_strings"]])}; do
        parse_cmdline_str "$string"
    done
    einfo "Parsed cmdline: $cmdline"
    """


def export_exports(self) -> list[str]:
    """Returns a shell script exporting all exports defined in the exports key.
    Sets 'exported' to 1 once done.
    If 'exported' is set, returns early.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        self["exports"]["VERSION"] = version(__package__.split(".")[0])
    except PackageNotFoundError:
        self["exports"]["VERSION"] = 9999

    check_lines = ["if check_var exported; then", '    edebug "Exports already set, skipping"', "    return", "fi"]
    export_lines = [f'setvar "{key}" "{value}"' for key, value in self["exports"].items()]

    return check_lines + export_lines + ["setvar exported 1"]
