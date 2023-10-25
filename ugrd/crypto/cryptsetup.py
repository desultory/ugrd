__author__ = 'desultory'

__version__ = '0.4.4'


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


def crypt_init(self):
    """
    Generates the bash script portion to prompt for keys
    """
    out = [r'echo -e "\n\n\nPress enter to start drive decryption.\n\n\n"', "read -sr"]
    for name, parameters in self.config_dict['cryptsetup'].items():
        self.logger.debug("Processing cryptsetup volume: %s" % name)

        key_type = parameters.get('key_type', self.config_dict.get('key_type'))

        partition_location_cmd = f"blkid -t UUID='{parameters['uuid']}' -s TYPE -o device"

        out += [f"echo 'Attempting to unlock device: {name}'"]

        if key_type == 'gpg':
            out += [f"echo 'Enter passphrase for key file: {parameters['key_file']}'"]
            out += [f"gpg --decrypt {parameters['key_file']} | cryptsetup open --key-file - $({partition_location_cmd}) {name}"]
        elif key_type == 'keyfile':
            out += [f"cryptsetup open --key-file {parameters['key_file']} $({partition_location_cmd}) {name}"]
        else:
            out += [f"cryptsetup open --tries 5 $({partition_location_cmd}) {name}"]
    return out


def copy_libgcc(self):
    """
    Copies libgcc_s.so
    """
    from subprocess import run

    ldconfig = run(['ldconfig', '-p'], capture_output=True).stdout.decode('utf-8').split("\n")
    libgcc = [lib for lib in ldconfig if 'libgcc_s' in lib and 'libc6,x86-64' in lib][0]
    source_path = libgcc.partition('=> ')[-1]
    destination_path = self.out_dir / 'lib64'

    self._copy(source_path, destination_path)
    self.logger.info("Copied libgcc from %s to %s" % (source_path, destination_path))

