__author__ = 'desultory'
__version__ = '1.1.2'

from zenlib.util import contains


@contains('sc_public_key', "Smartcard public key file not specified (sc_public_key)", raise_exception=True)
def fetch_keys(self) -> None:
    """ Adds the GGP public key file to the list of dependencies. """
    self.logger.info("Adding GPG public key file to dependencies: %s", self['sc_public_key'])
    self['dependencies'] = self['sc_public_key']


@contains('sc_public_key', "Smartcard public key file not specified (sc_public_key)", raise_exception=True)
def import_keys(self) -> str:
    """ Import GPG public keys at runtime. """
    return f'einfo "Importing GPG keys: $(gpg --import {self['sc_public_key']} 2>&1)"'

