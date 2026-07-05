__author__ = "desultory"
__version__ = "1.1.4"

from ugrd import InitramfsProtocol


def start_agent(self: InitramfsProtocol) -> str:
    """Start the GPG agent."""
    args = (" " + " ".join(self["gpg_agent_args"])) if self["gpg_agent_args"] else ""
    return f'einfo "Starting GPG agent: $(gpg-agent{args} 2>&1)"'
