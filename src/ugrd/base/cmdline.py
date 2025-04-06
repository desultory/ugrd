__author__ = "desultory"
__version__ = "4.1.0"

from importlib.metadata import PackageNotFoundError, version


def parse_cmdline_bool(self) -> str:
    """Returns a shell script to parse a boolean value from /proc/cmdline
    The only argument is the name of the variable to be read/set

    If the boolean is present in /proc/cmdline, the variable is set to 1.

    Otherwise, if it's set in the environment,
    set the variable to 1 if it's anything other than 0, and 0 if it is 0.
    """
    return r"""
    edebug "Parsing cmdline bool: $1"
    if grep -qE "(^|\s)$1(\s|$)" /proc/cmdline; then
        setvar "$1" 1
        edebug "[$1] Got cmdline bool: 1"
    else
        env_val=$(eval printf '%s' "\$$1")
        if [ -n "$env_val" ] && [ "$env_val" != "0" ]; then
            edebug "[$1] Enabling cmdline bool from environment with value: ${env_val}"
            setvar "$1" 1
        else
            edebug "[$1] Disabling cmdline bool with value: ${env_val}"
            setvar "$1" 0
        fi
    fi
    """


def parse_cmdline_str(self) -> str:
    """Returns a shell script to parse a string value from the environment.
    The kernel should pass option=value pairs from the cmdline to the environment of the initramfs init.

    The only argument is the name of the variable to be read/set

    Checks if that variable is set in the environment, and if so, sets it to the value.

    If the variable is not set in the environment, checks /proc/cmdline for the variable.
    This may be the case if not PID 1.
    """
    return r"""
    edebug "Parsing cmdline string: $1"

    val=$(eval printf '%s' "\$$1")  # Get the value of the variable
    if [ -n "$val" ]; then
        edebug "[$1] Got cmdline string from environment: ${val}"
        setvar "$1" "$val"
    else
        # If the variable is not set in the environment, check /proc/cmdline
        val=$(grep -oP "(?<=^|\s)$1=\K[^ ]+" /proc/cmdline)
        if [ -n "$val" ]; then
            edebug "[$1] Got cmdline string: ${val}"
            setvar "$1" "$val"
        fi
    fi
    """


def parse_cmdline(self) -> str:
    """Returns shell script to parse /proc/cmdline

    The portion before '--', if any, is the initramfs cmdline;
    the portion after '--' are arguments for the system init.

    The kernel will pass option=value pairs to the environment of the initramfs init.
    These can be processed into variables for ugrd.
    Named args are treated like boolean values, and are set to 1 if present.
    """
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
    try:
        self["exports"]["VERSION"] = version(__package__.split(".")[0])
    except PackageNotFoundError:
        self["exports"]["VERSION"] = 9999

    check_lines = ["if check_var exported; then", '    edebug "Exports already set, skipping"', "    return", "fi"]
    export_lines = [f'setvar "{key}" "{value}"' for key, value in self["exports"].items()]

    return check_lines + export_lines + ["setvar exported 1"]
