__author__ = 'desultory'
__version__ = '0.5.1'


from zen_util import check_dict


@check_dict('sc_public_key', raise_exception=True, message="Smartcard public key file not specified (sc_public_key)")
def fetch_keys(self) -> None:
    self.logger.info("Adding GPG public key file to dependencies: %s", self['sc_public_key'])
    self['dependencies'] = self['sc_public_key']


def check_card(self) -> str:
    """ Check if a smartcard is present. """
    return "gpg --card-status"


@check_dict('sc_public_key', raise_exception=True, message="Smartcard public key file not specified (sc_public_key)")
def import_keys(self) -> str:
    """ Import GPG public keys. """
    return f"gpg --import {self['sc_public_key']}"

