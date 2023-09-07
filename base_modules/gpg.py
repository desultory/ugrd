__author__ = 'desultory'

__version__ = '0.2.0'


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
        return [f"gpg --import {self.config_dict['gpg_public_key']}"]
    else:
        return []


def symlink_pinentry(self):
    """
    Symlink pinentry
    """
    pinentry = self.config_dict.get('pinentry', 'pinentry-tty')
    return [f"ln -s /usr/bin/{pinentry} /usr/bin/pinentry"]


def set_gpg_tty(self):
    """
    Set GPG_TTY
    """
    tty_path = self.config_dict.get('gpg_tty_path', '/dev/console')
    return [f'export GPG_TTY={tty_path}']
