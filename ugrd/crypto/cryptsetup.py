__author__ = 'desultory'

__version__ = '0.4.6'


def _process_cryptsetup(self, config_dict):
    """
    Processes the cryptsetup configuration
    """
    self.logger.debug("Processing cryptsetup configuration: %s" % config_dict)
    for values in config_dict.values():
        if values.get('key_type') == 'gpg':
            self.logger.info("Key type is GPG, adding gpg to mod_depends")
            self['mod_depends'] = 'ugrd.crypto.gpg'

    self['cryptsetup'].update(config_dict)


def configure_library_dir(self):
    """
    exports the libtary path for cryptsetup
    """
    return 'export LD_LIBRARY_PATH=/lib64'


def get_crypt_sources(self):
    """
    Goes through each cryptsetup device, sets $CRYPTSETUP_SOURCE_NAME to the source device
    """
    out = []
    for name, parameters in self.config_dict['cryptsetup'].items():
        blkid_command = f"CRYPTSETUP_DEVICE_{name}=$(blkid --match-token UUID='{parameters['uuid']}' --match-tag TYPE --output device)"
        check_command = f'if [ -z "$CRYPTSETUP_DEVICE_{name}" ]; then echo "Unable to resolve UUID for {name}"; bash; fi'
        out += [f"\necho 'Attempting to get device path for {name}'", blkid_command, check_command]

    return out


def crypt_init(self):
    """
    Generates the bash script portion to prompt for keys
    """
    out = [r'echo -e "\n\n\nPress enter to start drive decryption.\n\n\n"', "read -sr"]
    for name, parameters in self.config_dict['cryptsetup'].items():
        self.logger.debug("Processing cryptsetup volume: %s" % name)

        key_type = parameters.get('key_type', self.config_dict.get('key_type'))

        out += [f"echo 'Attempting to unlock device: {name}'"]

        cryptsetup_command = ""

        if key_type == 'gpg':
            out += [f"echo 'Enter passphrase for key file: {parameters['key_file']}'"]
            cryptsetup_command += f'gpg --decrypt {parameters["key_file"]} | cryptsetup open --key-file -'
        elif key_type == 'keyfile':
            cryptsetup_command += f'cryptsetup open --key-file {parameters["key_file"]}'
        else:
            cryptsetup_command += 'cryptsetup open --tries 5'

        if header_file := parameters.get('header_file'):
            cryptsetup_command += f' --header {header_file}'

        cryptsetup_command += f' $CRYPTSETUP_DEVICE_{name} {name}'

        out += [cryptsetup_command]
    return out


def copy_libgcc(self):
    """
    Copies libgcc_s.so
    """
    from subprocess import run
    from pathlib import Path

    ldconfig = run(['ldconfig', '-p'], capture_output=True).stdout.decode('utf-8').split("\n")
    libgcc = [lib for lib in ldconfig if 'libgcc_s' in lib and 'libc6,x86-64' in lib][0]
    source_path = Path(libgcc.partition('=> ')[-1])
    self.logger.debug("Source path for libgcc_s: %s" % source_path)

    self._copy(source_path, f"/lib64/{source_path.name}")

