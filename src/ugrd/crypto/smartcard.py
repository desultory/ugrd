__author__ = 'desultory'
__version__ = '1.0.0'


from zenlib.util import check_dict


@check_dict('sc_public_key', raise_exception=True, message="Smartcard public key file not specified (sc_public_key)")
def fetch_keys(self) -> None:
    self.logger.info("Adding GPG public key file to dependencies: %s", self['sc_public_key'])
    self['dependencies'] = self['sc_public_key']


@check_dict('sc_public_key', raise_exception=True, message="Smartcard public key file not specified (sc_public_key)")
def import_keys(self) -> str:
    """ Import GPG public keys. """
    return f"gpg --import {self['sc_public_key']}"

