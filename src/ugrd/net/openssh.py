__version__ = "0.1.0"

from pathlib import Path
from typing import Union

from zenlib.util import contains


def kill_ssh(self) -> str:
    """Returns shell lines to kill the ssh server if the switch_root_target is mounted"""
    return """
    if [ -n "$(awk '$2 == "'"$(cat /run/ugrd/SWITCH_ROOT_TARGET)"'" {print $2}' /proc/mounts)" ]; then
        einfo "Switch root target mounted, killing sshd."
        if [ -f /run/sshd.pid ]; then
            kill $(cat /run/sshd.pid)
            edebug "Deleting ssh PID file: /run/sshd.pid [$(rm -f /run/sshd.pid)]"
        else
            ewarning "No ssh PID file found, cannot kill sshd."
        fi
        return
    fi
    eerror "Switch root target not mounted after ssh init, ending session"
    rd_fail
    """


def _process_openssh_authorized_keys(self, authorized_key_path: Union[str, Path]):
    """Sets the openssh_authorized_keys to the path of the authorized_keys file"""
    authorized_key_path = Path(authorized_key_path)
    if not authorized_key_path.exists():
        raise FileNotFoundError(f"[openssh] Authorized_keys file not found at: {authorized_key_path}")
    self.data["openssh_authorized_keys"] = authorized_key_path


@contains("openssh_authorized_keys", raise_exception=True)
def add_openssh_keys(self):
    """Adds public keys to the root authorized_keys file"""
    self["copies"] = {
        "openssh_authorized_keys": {
            "source": self["openssh_authorized_keys"],
            "destination": "/root/.ssh/authorized_keys",
        }
    }


def ssh_finalize(self):
    """ Create a passwd entry for root if it doesn't exist, chmod 0600 the authorized_keys file """
    self._write("etc/passwd", "root:x:0:0:root:/root:/bin/sh\n", append=True)
    self._write("etc/passwd", "sshd:x:22:22:ssh user:/var/empty:/sbin/nologin\n", append=True)
    authorized_keys_file = self._get_build_path(self["copies"]["openssh_authorized_keys"]["destination"])
    authorized_keys_file.chmod(0o600)
    self._write("etc/ssh/sshd_config", "PermitRootLogin yes\n", append=True)

def sshd_init(self):
    """Returns a shell script to start init_main using openssh"""

    custom_init_contents = [
        self["shebang"],
        f'einfo "Starting ugrd openssh module v{__version__}"',
        "print_banner",
        *self.generate_init_main(),
        "kill_ssh",
    ]

    run_init = [  # Run sshd in the foreground
        "einfo Generating openssh host keys",
        "ssh-keygen -A || rd_fail",
        "einfo Starting openssh server",
        f"$(command -v sshd) -D -o ForceCommand=/{self['_custom_init_file']} || rd_fail",
    ]

    return run_init, custom_init_contents
