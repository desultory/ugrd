__author__ = "desultory"
__version__ = "7.3.0"

from pathlib import Path
from shutil import which

from ugrd.exceptions import AutodetectError, ValidationError
from zenlib.util import colorize as c_
from zenlib.util import contains, unset


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

def _process_log_file(self, log_file: Path | str) -> None:
    """Sets the log_file."""
    self.data["log_file"] = Path(log_file)
    self["exports"]["ugrd_log_file"] = str(self["log_file"])


@contains("hostonly", "Skipping init_target autodetection, hostonly is not set.", log_level=30)
@contains("autodetect_init", log_level=30)
@unset("init_target", "init_target is already set, skipping autodetection.", log_level=30)
def autodetect_init(self) -> None:
    """Autodetects the init_target.
    Attempts to find the "init" binary using which,
    if this fails, read /proc/1/exe to find the init binary.
    """
    if init := which("init"):
        self.logger.info("Detected init at: %s", c_(init, "cyan", bright=True))
        self["init_target"] = init
        return

    self.logger.info(f"No init found in PATH, checking {c_('/proc/1/exe', 'green')}")
    try:
        init = Path("/proc/1/exe").readlink()
        init = init.resolve()  # Resolve the symlink to get the actual path
        self.logger.info("Detected from process 1: %s", c_(init, "cyan", bright=True))
        self["init_target"] = init
        return
    except PermissionError:
        self.logger.eror("Unable to read /proc/1/exe, permission denied.")

    raise AutodetectError("init_target is not specified and could not be detected.")


@unset("shebang", "shebang is already set.", log_level=10)
def set_shebang(self) -> None:
    """If the shebang is not set, sets it to:
    #!/bin/sh {self["shebang_args"]}
    """
    self["shebang"] = f"#!/bin/sh {self['shebang_args']}"
    self.logger.info("Setting shebang to: %s", c_(self["shebang"], "cyan", bright=True))


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
    return r"""
    if [ $$ -ne 1 ] ; then
        eerror "Cannot switch_root from PID: $$, exiting."
        exit 1
    fi
    switch_root_target=$(readvar SWITCH_ROOT_TARGET)
    if ! grep -q " ${switch_root_target} " /proc/mounts ; then
        rd_fail "Root not found at: $switch_root_target"
    fi
    if [ -z "$(readvar init)" ]; then
        einfo "init= is not set, running autodetection."
        _find_init || rd_fail "Unable to find init."
    fi
    init_target=$(readvar init)
    einfo "Checking root mount: $switch_root_target"
    if [ ! -e "${switch_root_target}${init_target}" ] ; then
        ewarn "$init_target not found at: $switch_root_target"
        einfo "Target root contents:\n$(ls -l "$switch_root_target")"
        _find_init || rd_fail "Unable to find init."  # Redefines init on success
        init_target=$(readvar init)
    fi
    einfo "Switching root to: $switch_root_target $init_target"
    klog "[UGRD $(readvar VERSION)] Running init: $init_target"
    einfo "Cleaning up /run/ugrd"
    edebug "$(rm -rfv /run/ugrd)"
    exec switch_root "$switch_root_target" "$init_target"
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
        'prompt_user "Press space to display debug info."',
        r'eerror "Kernel version: $(cat /proc/version)"',
        r'eerror "Kernel command line: $(cat /proc/cmdline)"',
        r'eerror "Loaded modules:\n$(cat /proc/modules)"',
        r'eerror "Block devices:\n$(blkid)"',
        r'eerror "Mounts:\n$(mount)"',
        'if [ "$(readvar ugrd_recovery)" = "1" ]; then',
        '    einfo "Entering recovery shell"',
    ]
    if "ugrd.base.plymouth" in self["modules"]:
        output += [
            "    if plymouth --ping; then",
            '        plymouth display-message --text="Entering recovery shell"',
            "        plymouth hide-splash",
            "        setsid -c sh -i -l",
            "        plymouth show-splash",
            "    else",
            "        setsid -c sh -i -l",
            "    fi",
        ]
    else:
        output += ["    setsid -c sh -i -l"]
    output += ["fi", 'prompt_user "Press space to restart init."', "rd_restart"]
    return output


def setvar(self) -> str:
    """Returns a shell function that sets a variable in /run/ugrd/{name}."""
    return """
    if check_var ugrd_debug; then
        edebug "Setting $1 to: $2"
    else
        rd_log "Setting $1 to: $2"
    fi
    printf "%s" "$2" > "/run/ugrd/${1}"
    """


def readvar(self) -> str:
    """Returns a shell function that reads a variable from /run/ugrd/{name}.
    The second arg can be a default value.
    If no default is supplied, and the variable is not found, it returns an empty string.
    """
    return 'cat "/run/ugrd/${1}" 2>/dev/null || printf "%s" "${2}"'


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


def wait_for_space(self) -> str:
    """Returns a shell script that reads a single character from stdin.
    If an argument is passed, use that as a timeout in seconds.
    If space is pressed, return 0, otherwise return 1.
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
        " " ) return 0 ;;
        *) return 1 ;;
    esac
    """


def prompt_user(self) -> list[str]:
    """Returns a shell function that pauses until the user presses space.
    The first argument is the prompt message.
    The second argument is the timeout in seconds.

    If the timeout is not set, or set to zero, loops wait_for_space until space is pressed.

    if plymouth is running, run 'plymouth display-message --text="$prompt" instead of echo.
    """
    output = ['prompt=${1:-"Press space to continue."}']
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
        """if [ -z "$2" ] || [ "$(echo "$2 > 0" | bc)" -eq 0 ]; then""",
        '    while ! wait_for_space; do',
        '        ewarn "Invalid input, press space to continue."',
        '    done',
        '    return 0',
        'fi',
        'wait_for_space "$2"',
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

def rd_log(self) -> str:
    """ If ugrd_log_file is set, logs a message to the log file.
    Always log under /run
    """
    return r"""
    log_file="$(readvar ugrd_log_file)"
    if [ -n "${log_file}" ]; then
        printf "%b\n" "${*}" >> "/run/${log_file}"
    fi
    """


# To feel more at home
def edebug(self) -> str:
    """Returns a shell function like edebug."""
    return r"""
    output="$(printf "%b" "${*}")"
    rd_log "DEBUG: ${output}"
    if check_var quiet; then
        return
    fi
    if [ "$(readvar ugrd_debug)" != "1" ]; then
        return
    fi
    printf "\033[1;34m *\033[0m %b\n" "${output}"
    """


def einfo(self) -> list[str]:
    """Returns a shell function like einfo."""
    output = ['output="$(printf "%b" "${*}")"', 'rd_log "INFO: ${output}"']
    if "ugrd.base.plymouth" in self["modules"]:
        output += [
            "if plymouth --ping; then",
            '    plymouth display-message --text="${output}"',
            "    return",
            "fi",
        ]

    output += ["if check_var quiet; then", "    return", "fi", r'printf "\033[1;32m *\033[0m %b\n" "${output}"']
    return output


def ewarn(self) -> list[str]:
    """Returns a shell function like ewarn.
    If plymouth is running, it displays a message instead of echoing.
    """
    output = ['output="$(printf "%b" "${*}")"', 'rd_log "WARN: ${output}"']
    if "ugrd.base.plymouth" in self["modules"]:
        output += [
            "if plymouth --ping; then",  # Always show the message if plymouth is running
            '    plymouth display-message --text="Warning: ${output}"',
            "    return",  # Return early so echo doesn't leak
            "fi",
        ]

    output += [
        "if check_var quiet; then",
        "    return",
        "fi",
        r'printf "\033[1;33m *\033[0m %b\n" "${output}"',
    ]
    return output


def eerror(self) -> list[str]:
    """Returns a shell function like eerror."""
    output = ['output="$(printf "%b" "${*}")"', 'rd_log "ERROR: ${output}"']
    if "ugrd.base.plymouth" in self["modules"]:
        output += [
            "if plymouth --ping; then",
            '    plymouth display-message --text="Error: ${output}"',
            "    return",
            "fi",
        ]
    else:
        output += [r'printf "\033[1;31m *\033[0m %b\n" "${output}"']
    return output
