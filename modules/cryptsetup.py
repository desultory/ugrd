__author__ = 'desultory'
__version__ = '0.2.0'


def configure_library_dir(self):
    """
    exports the libtary path for cryptsetup
    """
    return ['export LD_LIBRARY_PATH=/lib64']


def crypt_init(self):
    """
    Generates the bash script portion to prompt for keys
    """
    out = ["read -p 'Press enter to start drive decryption'"]
    for root_device, parameters in self.config_dict['root_devices'].items():
        self.logger.debug("Processing root device: %s" % root_device)
        key_type = parameters.get('key_type', self.config_dict.get('key_type'))
        partition_location_cmd = f"blkid -t UUID='{parameters['uuid']}' -s TYPE -o device"
        if key_type == 'gpg':
            out += [f"gpg --decrypt {parameters['key_file']} | cryptsetup open --key-file - $({partition_location_cmd}) {root_device}"]
        else:
            out += [f"cryptsetup open --key-file {parameters['key_file']} $({partition_location_cmd}) {root_device}"]
    return out


def copy_libgcc(self):
    """
    Copies libgcc_s.so
    """
    from subprocess import run
    from shutil import copy2
    ldconfig = run(['ldconfig', '-p'], capture_output=True).stdout.decode('utf-8').split("\n")
    libgcc = [lib for lib in ldconfig if 'libgcc_s' in lib and 'libc6,x86-64' in lib][0]
    source_path = libgcc.partition('=> ')[-1]
    destination_path = self.out_dir + '/lib64'

    copy2(source_path, destination_path)
    self.logger.info("Copied libgcc from %s to %s" % (source_path, destination_path))

