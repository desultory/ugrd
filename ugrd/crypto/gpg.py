__author__ = 'desultory'

__version__ = '0.3.0'


def fetch_keys(self):
    """
    Pulls the GPG keys into the initramfs
    """
    if 'gpg_public_key' in self.config_dict:
        public_key = self.config_dict['gpg_public_key']
        self.logger.info("Adding GPG public key file to dependencies: %s", public_key)
        self.config_dict['dependencies'].append(public_key)
    else:
        self.logger.debug("No GPG public key specified, skipping")


def import_keys(self):
    """
    Import GPG public keys
    """
    if 'gpg_public_key' in self.config_dict:
        return f"gpg --import {self.config_dict['gpg_public_key']}"


def symlink_pinentry(self):
    """
    Symlink pinentry
    """
    pinentry = self.config_dict.get('pinentry', 'pinentry-tty')
    return f"ln -s /usr/bin/{pinentry} /usr/bin/pinentry"


def start_agent(self):
    """
    Start the GPG agent
    """
    return "gpg-agent"
