__author__ = 'desultory'
__version__ = '0.2.2'


def fetch_keys(self) -> None:
    """
    Pulls the GPG keys into the initramfs.
    """
    if 'sc_public_key' in self.config_dict:
        public_key = self.config_dict['sc_public_key']
        self.logger.info("Adding GPG public key file to dependencies: %s", public_key)
        self.config_dict['dependencies'] = public_key
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
    if 'sc_public_key' in self.config_dict:
        return f"gpg --import {self.config_dict['sc_public_key']}"

