__author__ = "desultory"
__version__ = "6.6.2"

from pathlib import Path
from shutil import which

from ugrd import AutodetectError, ValidationError
from zenlib.util import colorize, contains, unset


@contains("validate")
@contains("hostonly", "Skipping init validation, as hostonly is not set", log_level=30)
def check_init_target(self) -> None:
    if not self["init_target"].exists():
        raise ValidationError("init_target not found at: %s" % self["init_target"])


def _process_init_target(self, target: Path) -> None:
    if not isinstance(target, Path):
        target = Path(target).resolve()
    if "systemd" in str(target) and "ugrd.fs.fakeudev" not in self["modules"]:
        self.logger.warning("[systemd] Auto-enabling 'ugrd.fs.fakeudev'. This module is experimental.")
        self["modules"] = "ugrd.fs.fakeudev"
    self.data["init_target"] = target
    self["exports"]["init"] = self["init_target"]


def _process_loglevel(self, loglevel: int) -> None:
    """Sets the loglevel."""
    self.data["loglevel"] = int(loglevel)
    self["exports"]["loglevel"] = loglevel


def _get_shell_path(self, shell_name) -> Path:
    """Gets the real path to the shell binary."""
    if shell := which(shell_name):
        return Path(shell).resolve()
    else:
        raise AutodetectError(f"Shell '{shell_name}' not found.")


@contains("hostonly", "Skipping init_target autodetection, hostonly is not set.", log_level=30)
@contains("autodetect_init", log_level=30)
@unset("init_target", "init_target is already set, skipping autodetection.", log_level=30)
def autodetect_init(self) -> None:
    """Autodetects the init_target."""
    if init := which("init"):
        self.logger.info("Detected init at: %s", colorize(init, "cyan", bright=True))
        self["init_target"] = init
    else:
        raise AutodetectError("init_target is not specified and could not be detected.")


@unset("shebang", "shebang is already set.", log_level=10)
def set_shebang(self) -> None:
    """If the shebang is not set, sets it to:
    #!/bin/sh {self["shebang_args"]}
    """
    self["shebang"] = f"#!/bin/sh {self['shebang_args']}"
    self.logger.info("Setting shebang to: %s", colorize(self["shebang"], "cyan", bright=True))


def set_init_final_order(self) -> None:
    """Adds a "before" do_switch_root order to everything in the init_final hook, excep do_switch_root."""
    for hook in self["imports"]["init_final"]:
        if hook.__name__ != "do_switch_root":
            self["import_order"] = {"before": {hook.__name__: "do_switch_root"}}


def export_switch_root_target(self) -> None:
    """Adds SWITCH_ROOT_TARGET to exports.
    Uses switch_root_target if set, otherwise uses the rootfs."""
    switch_root_target = self["switch_root_target"]
    if str(switch_root_target) == ".":  # Handle empty Path
        switch_root_target = self["mounts"]["root"]["destination"]
    self["exports"]["SWITCH_ROOT_TARGET"] = switch_root_target


def _find_init(self) -> str:
    """Returns a shell script to find the init_target."""
    return """
    for init_path in "/sbin/init" "/bin/init" "/init"; do
        if [ -e "$(readvar SWITCH_ROOT_TARGET)$init_path" ] ; then
            einfo "Found init at: $(readvar SWITCH_ROOT_TARGET)$init_path"
            setvar init "$init_path"
            return
        fi
    done
    eerror "Unable to find init."
    return 1
    """


def set_loglevel(self) -> str:
    """Returns shell lines to set the log level."""
    return "readvar loglevel > /proc/sys/kernel/printk"


@contains("validate", "Skipping switch_root validation, as validation is disabled.", log_level=30)
def check_switch_root_last(self) -> None:
    """Validates that do_switch_root is the last function in init_final"""
    if not self["imports"]["init_final"][-1].__name__ == "do_switch_root":
        raise ValidationError("do_switch_root must be the last function in init_final.")


def do_switch_root(self) -> str:
    """Should be the final statement, switches root.
    Ensures it is PID 1, and that the init_target exists.

    Checks if the switch_root target is mounted, and that it contains an init.

    If an init is not set, it will try to autodetect it.
    If it fails to find an init, rd_fail is called.

    If not, it restarts UGRD.
    """
    from importlib.metadata import version

    return fr"""
    if [ $$ -ne 1 ] ; then
        eerror "Cannot switch_root from PID: $$, exiting."
        exit 1
    fi
    if ! grep -q " $(readvar SWITCH_ROOT_TARGET) " /proc/mounts ; then
        rd_fail "Root not found at: $(readvar SWITCH_ROOT_TARGET)"
    fi
    if [ -z "$(readvar init)" ]; then
        einfo "Init is no set, running autodetection."
        _find_init || rd_fail "Unable to find init."
    fi
    init_target=$(readvar init)
    einfo "Checking root mount: $(readvar SWITCH_ROOT_TARGET)"
    if [ ! -e "$(readvar SWITCH_ROOT_TARGET)${{init_target}}" ] ; then
        ewarn "$init_target not found at: $(readvar SWITCH_ROOT_TARGET)"
        einfo "Target root contents:\n$(ls -l "$(readvar SWITCH_ROOT_TARGET)")"
        if _find_init ; then  # This redefines the var, so readvar is used instead of $init_target
            einfo "Switching root to: $(readvar SWITCH_ROOT_TARGET) $(readvar init)"
            klog "[UGRD {version("ugrd")}] Running init: $(readvar init)"
            exec switch_root "$(readvar SWITCH_ROOT_TARGET)" "$(readvar init)"
        fi
        rd_fail "Unable to find init."
    else
        einfo "Switching root to: $(readvar SWITCH_ROOT_TARGET) $init_target"
        klog "[UGRD {version("ugrd")}] Running init: $init_target"
        exec switch_root "$(readvar SWITCH_ROOT_TARGET)" "$init_target"
    fi
    """


def rd_restart(self) -> str:
    """Restart the initramfs, exit if not PID 1, otherwise exec /init."""
    return """
    if [ "$$" -eq 1 ]; then
        einfo "Restarting init"
        exec /init ; exit
    else
        ewarn "PID is not 1, exiting: $$"
        exit 1
    fi
    """


def rd_fail(self) -> list[str]:
    """Function for when the initramfs fails to function.
    If a string is passed, it will be displayed as the error message.
    Waits for user input, then displays debug info.
    If the plymouth module is loaded, hides the splash before allowing the user to enter a shell.
    """
    output = [
        'if [ -n "$1" ]; then',
        '    eerror "Failure: $1"',
        "else",
        '    eerror "UGRD failed."',
        "fi",
        'prompt_user "Press enter to display debug info."',
        r'eerror "Loaded modules:\n$(cat /proc/modules)"',
        r'eerror "Block devices:\n$(blkid)"',
        r'eerror "Mounts:\n$(mount)"',
        'if [ "$(readvar recovery)" = "1" ]; then',
        '    einfo "Entering recovery shell"',
    ]
    if "ugrd.base.plymouth" in self["modules"]:
        output += [
            "    if plymouth --ping; then",
            '        plymouth display-message --text="Entering recovery shell"',
            "        plymouth hide-splash",
            "        sh -l",
            "        plymouth show-splash",
            "    else",
            "        sh -l",
            "    fi",
        ]
    else:
        output += ["    sh -l"]
    output += ["fi", 'prompt_user "Press enter to restart init."', "rd_restart"]
    return output


def setvar(self) -> str:
    """Returns a shell function that sets a variable in /run/vars/{name}."""
    return """
    if check_var debug; then
        edebug "Setting $1 to $2"
    fi
    printf "%s" "$2" > "/run/vars/${1}"
    """


def readvar(self) -> str:
    """Returns a shell function that reads a variable from /run/vars/{name}.
    The second arg can be a default value.
    If no default is supplied, and the variable is not found, it returns an empty string.
    """
    return 'cat "/run/vars/${1}" 2>/dev/null || echo "${2}"'


def check_var(self) -> str:
    """Returns a shell function that checks the value of a variable.
    if it's not set, tries to read the cmdline."""
    return r"""
    value=$(readvar "$1")
    if [ -z "$value" ]; then
        cmdline=$(awk -F '--' '{print $1}' /proc/cmdline)  # Get everything before '--'
        if echo "$cmdline" | grep -qE "(^|\s)$1(\s|$)"; then
            return 0
        fi
        return 1
    fi
    if [ "$value" = "1" ]; then
        return 0
    fi
    return 1
    """


def wait_enter(self) -> str:
    """Returns a shell script that reads a single character from stdin.
    If an argument is passed, use that as a timeout in seconds.
    If enter is pressed, return 0, otherwise return 1.
    """
    return r"""
    tty_env=$(stty -g)
    t=$(printf "%.0f" "$(echo "${1:-0} * 10" | bc)")
    if [ "$t" -gt 300 ]; then
        stty raw -echo min 0 time 300
    elif [ "$t" -gt 0 ]; then
        stty raw -echo min 0 time "$t"
    else
        stty raw -echo
    fi
    char="$(dd bs=1 count=1 2>/dev/null)"
    stty "$tty_env"
    case "$char" in
        $(printf '\r')) return 0 ;;
        *) return 1 ;;
    esac
    """


def prompt_user(self) -> list[str]:
    """Returns a shell function that pauses until the user presses enter.
    The first argument is the prompt message.
    The second argument is the timeout in seconds.

    if plymouth is running, run 'plymouth display-message --text="$prompt" instead of echo.
    """
    output = ['prompt=${1:-"Press enter to continue."}']
    if "ugrd.base.plymouth" in self["modules"]:
        output += [
            "if plymouth --ping; then",
            '    plymouth display-message --text="$prompt"',
            "else",
            r'    printf "\033[1;35m *\033[0m %s\n" "$prompt"',
            "fi",
        ]
    else:
        output += [r'printf "\033[1;35m *\033[0m %s\n" "$prompt"']
    output += [
        'wait_enter "$2"',
        'return "$?"',
    ]
    return output


def retry(self) -> str:
    """Returns a shell function that retries a command some number of times.
    The first argument is the number of retries. if 0, it retries 100 times.
    The second argument is the timeout in seconds.
    The remaining arguments represent the command to run.
    """
    return """
    retries=${1}
    timeout=${2}
    shift 2
    if [ "$retries" -eq 0 ]; then
        "$@"  # If retries is 0, just run the command
        return "$?"
    elif [ "$retries" -lt 0 ]; then
        retries=1000
    fi
    i=-1; while [ "$((i += 1))" -lt "$retries" ]; do
        if "$@"; then
            return 0
        fi
        ewarn "[${i}/${retries}] Failed: ${*}"
        if [ "$i" -lt "$((retries - 1))" ]; then
            prompt_user "Retrying in: ${timeout}s" "$timeout"
        fi
    done
    return 1
    """


def klog(self) -> str:
    """Logs a message to the kernel log."""
    return 'echo "${*}" > /dev/kmsg'


# To feel more at home
def edebug(self) -> str:
    """Returns a shell function like edebug."""
    return r"""
    if check_var quiet; then
        return
    fi
    if [ "$(readvar debug)" != "1" ]; then
        return
    fi
    printf "\033[1;34m *\033[0m %s\n" "${*}"
    """


def einfo(self) -> list[str]:
    """Returns a shell function like einfo."""
    if "ugrd.base.plymouth" in self["modules"]:
        output = [
            "if plymouth --ping; then",
            '    plymouth display-message --text="${*}"',
            "    return",
            "fi",
        ]
    else:
        output = []

    output += ["if check_var quiet; then", "    return", "fi", r'printf "\033[1;32m *\033[0m %s\n" "${*}"']
    return output


def ewarn(self) -> list[str]:
    """Returns a shell function like ewarn.
    If plymouth is running, it displays a message instead of echoing.
    """
    if "ugrd.base.plymouth" in self["modules"]:
        output = [
            "if plymouth --ping; then",  # Always show the message if plymouth is running
            '    plymouth display-message --text="Warning: ${*}"',
            "    return",  # Return early so echo doesn't leak
            "fi",
        ]
    else:
        output = []

    output += [
        "if check_var quiet; then",
        "    return",
        "fi",
        r'printf "\033[1;33m *\033[0m %s\n" "${*}"',
    ]
    return output


def eerror(self) -> str:
    """Returns a shell function like eerror."""
    if "ugrd.base.plymouth" in self["modules"]:
        return r"""
        if plymouth --ping; then
            plymouth display-message --text="Error: ${*}"
            return
        fi
        printf "\033[1;31m *\033[0m %s\n" "${*}"
        """
    else:
        return r'printf "\033[1;31m *\033[0m %s\n" "${*}"'
