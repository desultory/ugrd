__author__ = 'desultory'
__version__ = '0.4.0'


def fetch_keys(self) -> None:
    """
    Pulls the GPG keys into the initramfs.
    """
    if public_key := self.get('sc_public_key'):
        self.logger.info("Adding GPG public key file to dependencies: %s", public_key)
        self['dependencies'] = public_key
    else:
        self.logger.debug("No GPG public key specified, skipping")


def check_card(self) -> str:
    """
    Check if a smartcard is present.
    """
    return "gpg --card-status"


def import_keys(self) -> str:
    """
    Import GPG public keys.
    """
    if public_key := self.get('sc_public_key'):
        return f"gpg --import {public_key}"

