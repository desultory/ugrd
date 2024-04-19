__author__ = 'desultory'
__version__ = '0.6.0'


def _process_gpg_keyboxd(self, keyboxd_enabled: bool) -> None:
    """ Process the `gpg_keyboxd` configuration. """
    dict.__setitem__(self, 'gpg_keyboxd', keyboxd_enabled)
    if keyboxd_enabled:
        self['binaries'] = '/usr/libexec/keyboxd'


def start_agent(self) -> str:
    """ Start the GPG agent. """
    args = " ".join(self['gpg_agent_args']) if self['gpg_agent_args'] else ""
    return f"gpg-agent {args}"


def write_gpg_config(self):
    """ Write the GPG configuration file. """
    if not self['gpg_keyboxd']:
        self['gpg_common_conf'] = 'no-usekeyboxd'

    if self['gpg_common_conf']:
        self._write('/root/.gnupg/common.conf', self['gpg_common_conf'])
    else:
        self.logger.debug("No GPG common configuration provided.")
