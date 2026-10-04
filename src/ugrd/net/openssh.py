__author__ = "borisfaure"
__version__ = "0.1.0"

from pathlib import Path

from ugrd import InitramfsProtocol
from ugrd.exceptions import ValidationError
from zenlib.util import colorize as c_
from zenlib.util import contains

SESSION_SCRIPT = "openssh_unlock.sh"
SSHD_CONFIG = "etc/ssh/sshd_config"

# sshd re-execs these by compiled-in path (split out in OpenSSH 9.8 and 10.0)
SSHD_HELPERS = ["sshd-session", "sshd-auth"]


def _process_openssh_authorized_keys(self: InitramfsProtocol, authorized_keys: Path | str) -> None:
    """Validates and sets openssh_authorized_keys; an empty file would lock out all logins."""
    authorized_keys = Path(authorized_keys)
    if not authorized_keys.is_file():
        raise ValidationError(f"[openssh] authorized_keys file not found: {c_(authorized_keys, 'red')}")
    if not authorized_keys.read_text().strip():
        raise ValidationError(f"[openssh] authorized_keys file is empty: {c_(authorized_keys, 'red')}")
    self.data["openssh_authorized_keys"] = authorized_keys


def _process_openssh_host_keys_multi(self: InitramfsProtocol, host_key: Path | str) -> None:
    """Validates a pinned host key and adds it to openssh_host_keys; pinning keeps the fingerprint stable."""
    host_key = Path(host_key)
    if not host_key.is_file():
        raise ValidationError(f"[openssh] host key not found: {c_(host_key, 'red')}")
    if host_key.name.endswith(".pub"):
        raise ValidationError(f"[openssh] host key is a public key, use the private key: {c_(host_key, 'red')}")
    self["openssh_host_keys"].append(host_key)


def find_sshd_helpers(self: InitramfsProtocol) -> None:
    """Adds sshd-session/sshd-auth to the binaries; they live in distro-specific libexec dirs."""
    for helper in SSHD_HELPERS:
        for libexec in self["openssh_libexec_paths"]:
            candidate = Path(libexec) / helper
            if candidate.is_file():
                self.logger.info(f"[openssh] Found sshd helper: {c_(candidate, 'cyan')}")
                self["binaries"] = str(candidate)
                break
        else:  # only sshd itself is required; the helpers are newer additions
            self.logger.debug(f"[openssh] sshd helper not found, assuming it is not needed: {helper}")


@contains("openssh_authorized_keys", "openssh_authorized_keys must be set", raise_exception=True)
@contains("openssh_host_keys", "openssh_host_keys must be set", raise_exception=True)
def add_openssh_keys(self: InitramfsProtocol) -> None:
    """Copies the authorized_keys file and the pinned host keys into the initramfs.
    Pinned host keys are mandatory: without them the fingerprint changes on every boot, so the
    client cannot verify the server and an attacker could capture the passphrase."""
    self["copies"] = {
        "openssh_authorized_keys": {
            "source": self["openssh_authorized_keys"],
            "destination": "/root/.ssh/authorized_keys",
        }
    }

    for host_key in self["openssh_host_keys"]:
        self["copies"] = {
            f"openssh_host_key_{host_key.name}": {
                "source": host_key,
                "destination": f"/etc/ssh/{host_key.name}",
            }
        }
        public_key = host_key.with_name(host_key.name + ".pub")
        if public_key.is_file():  # sshd works without it, but logs its absence
            self["copies"] = {
                f"openssh_host_key_{public_key.name}": {
                    "source": public_key,
                    "destination": f"/etc/ssh/{public_key.name}",
                }
            }


def openssh_finalize(self: InitramfsProtocol) -> None:
    """Writes the passwd/group entries, sshd config and session script, then tightens key permissions.
    sshd always privseps, so its user must resolve; root's shell must match the init shebang."""
    self._write("etc/passwd", "root:x:0:0:root:/root:/bin/sh\n", append=True)
    self._write("etc/passwd", "sshd:x:22:22:sshd:/var/empty:/sbin/nologin\n", append=True)
    self._write("etc/group", "root:x:0:\nsshd:x:22:\ntty:x:5:\n", append=True)

    _write_sshd_config(self)
    _deploy_session_script(self)

    self._get_build_path("root/.ssh").chmod(0o700)
    self._get_build_path("root/.ssh/authorized_keys").chmod(0o600)
    for host_key in self["openssh_host_keys"]:  # StrictModes rejects world readable keys
        self._get_build_path(f"etc/ssh/{host_key.name}").chmod(0o600)


def _write_sshd_config(self: InitramfsProtocol) -> None:
    """Writes the sshd config.
    ForceCommand makes every session an unlock only, so no key grants a shell."""
    config = [
        f"Port {self['openssh_port']}",
        "PermitRootLogin prohibit-password",
        "AuthorizedKeysFile /root/.ssh/authorized_keys",
        f"ForceCommand /{SESSION_SCRIPT}",
        "PidFile /run/sshd.pid",
        "AllowUsers root",
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        # UsePAM is omitted: it defaults to no, and PAM-less sshd logs it as unsupported
        "UseDNS no",  # no resolver in the initramfs
        "PrintMotd no",
        "PrintLastLog no",
        "X11Forwarding no",
        "AllowAgentForwarding no",
        "AllowTcpForwarding no",
    ]

    for host_key in self["openssh_host_keys"]:
        config.append(f"HostKey /etc/ssh/{host_key.name}")

    if self["openssh_config"]:
        config += list(self["openssh_config"])

    self._write(SSHD_CONFIG, config + [""], chmod_mask=0o600)


def _deploy_session_script(self: InitramfsProtocol) -> None:
    """Writes the script sshd forces as the session command; it only unlocks, the console init does the rest.
    The functions it calls come from the profile, sourced by the shell shebang."""
    self._write(
        SESSION_SCRIPT,
        [
            self["shebang"],
            f'einfo "ugrd openssh remote unlock, module v{__version__}"',
            "crypt_init",
            # the console init cannot notice the unlock from its own prompt
            "nudge_crypt_prompt",
            'einfo "Unlock complete, the console init will continue booting"',
        ],
        chmod_mask=0o755,
    )


def nudge_crypt_prompt(self: InitramfsProtocol) -> str:
    """Returns a shell function which SIGINTs any waiting cryptsetup prompt.
    SIGINT, not SIGKILL, so the prompt's shell survives; /proc is walked as the image has no pgrep."""
    return """
    for _proc in /proc/[0-9]*; do
        _pid="${_proc##*/}"
        [ "$_pid" = "$$" ] && continue
        read -r _comm < "$_proc/comm" 2>/dev/null || continue
        if [ "$_comm" = "cryptsetup" ]; then
            einfo "Interrupting cryptsetup prompt: $_pid"
            kill -INT "$_pid" 2>/dev/null
        fi
    done
    """


def stop_sshd(self: InitramfsProtocol) -> str:
    """Returns a shell function which stops sshd and its sessions; sessions first, or one survives switch_root."""
    return """
    sshd_pid="$(readvar SSHD_PID)"
    if [ -z "$sshd_pid" ]; then
        ewarn "Unable to read SSHD_PID, not stopping sshd."
        return
    fi
    for _proc in /proc/[0-9]*; do
        _pid="${_proc##*/}"
        read -r _stat < "$_proc/stat" 2>/dev/null || continue
        # comm may contain spaces, so split after the last ") "
        _rest="${_stat##*) }"
        # shellcheck disable=SC2086
        set -- $_rest
        _ppid="$2"
        if [ "$_ppid" = "$sshd_pid" ]; then
            einfo "Stopping sshd session: $_pid"
            kill "$_pid" 2>/dev/null
        fi
    done
    einfo "Stopping sshd: $sshd_pid"
    kill "$sshd_pid"
    """


def start_sshd(self: InitramfsProtocol) -> list[str]:
    """Returns the shell lines which start sshd in the background; the console init continues to its own prompt."""
    args = ["-D", "-e", "-f", f"/{SSHD_CONFIG}"]
    if self["openssh_args"]:
        args += list(self["openssh_args"])

    self.logger.info(f"[openssh] Server arguments: {c_(' '.join(args), 'cyan')}")

    return [
        f'einfo "Starting sshd on port: {self["openssh_port"]}"',
        # sshd re-execs itself and needs an absolute path; merge_usr can move it, so resolve at runtime
        'sshd_bin="$(command -v sshd)"',
        # a missing sshd must not stop the boot
        'if [ ! -x "$sshd_bin" ]; then',
        '    ewarn "sshd not found, remote unlock is unavailable"',
        "    return",
        "fi",
        f"\"$sshd_bin\" {' '.join(args)} &",
        "sshd_pid=$!",
        'setvar SSHD_PID "$sshd_pid"',
    ]
