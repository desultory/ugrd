__author__ = 'desultory'
__version__ = '0.3.6'


def fetch_keys(self) -> None:
    """
    Pulls the GPG keys into the initramfs
    """
    if 'gpg_public_key' in self.config_dict:
        public_key = self.config_dict['gpg_public_key']
        self.logger.info("Adding GPG public key file to dependencies: %s", public_key)
        self.config_dict['dependencies'].append(public_key)
    else:
        self.logger.debug("No GPG public key specified, skipping")


def import_keys(self) -> str:
    """
    Import GPG public keys
    """
    if 'gpg_public_key' in self.config_dict:
        return f"gpg --import {self.config_dict['gpg_public_key']}"


def start_agent(self) -> str:
    """
    Start the GPG agent
    """
    args = " ".join(self.config_dict['gpg_agent_args']) if self.config_dict['gpg_agent_args'] else ""
    return f"gpg-agent {args}"
