__author__ = 'desultory'
__version__ = '0.5.0'


from zenlib.util.check_dict import check_dict


@check_dict('gpg_public_key', message="GPG public key file not specified, skipping")
def fetch_keys(self) -> None:
    """ Pulls the GPG keys into the initramfs. """
    self.logger.info("Adding GPG public key file to dependencies: %s", self['gpg_public_key'])
    self['dependencies'].append(self['gpg_public_key'])


@check_dict('gpg_public_key', message="GPG public key file not specified, skipping")
def import_keys(self) -> str:
    """ Import GPG public keys. """
    return f"gpg --import {self['gpg_public_key']}"


def start_agent(self) -> str:
    """ Start the GPG agent. """
    args = " ".join(self['gpg_agent_args']) if self['gpg_agent_args'] else ""
    return f"gpg-agent {args}"
