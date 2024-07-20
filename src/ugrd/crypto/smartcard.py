__author__ = 'desultory'
__version__ = '1.1.0'


def fetch_keys(self) -> None:
    """ Adds the GGP public key file to the list of dependencies. """
    self._dict_contains('sc_public_key', message="Smartcard public key file not specified (sc_public_key)", raise_exception=True)
    self.logger.info("Adding GPG public key file to dependencies: %s", self['sc_public_key'])
    self['dependencies'] = self['sc_public_key']


def import_keys(self) -> str:
    """ Import GPG public keys at runtime. """
    self._dict_contains('sc_public_key', message="Smartcard public key file not specified (sc_public_key)", raise_exception=True)
    return f"gpg --import {self['sc_public_key']}"

