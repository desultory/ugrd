__author__ = 'desultory'
__version__ = '1.1.0'


def start_agent(self) -> str:
    """ Start the GPG agent. """
    args = (' ' + " ".join(self['gpg_agent_args'])) if self['gpg_agent_args'] else ""
    return f"einfo gpg-agent{args}"

