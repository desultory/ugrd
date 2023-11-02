__author__ = 'desultory'

__version__ = '0.7.2'


CRYPTSETUP_PARAMETERS = ['key_type', 'partuuid', 'uuid', 'key_file', 'header_file', 'retries', 'key_command', 'reset_command', 'try_nokey']


def _process_cryptsetup_key_types_multi(self, key_type, config_dict):
    """
    Processes the cryptsetup key types.
    Updates the key type configuration if it already exists, otherwise creates a new key type.
    """
    self.logger.debug("[%s] Processing cryptsetup key type configuration: %s" % (key_type, config_dict))
    for parameter in config_dict:
        if parameter not in CRYPTSETUP_PARAMETERS:
            raise ValueError("Invalid parameter: %s" % parameter)

    if key_type in self['cryptsetup_key_types']:
        self.logger.debug("[%s] Updating key type configuration: %s" % (key_type, config_dict))
        self['cryptsetup_key_types'][key_type].update(config_dict)
    else:
        if 'key_command' not in config_dict:
            raise ValueError("Missing key_command for key type: %s" % config_dict)
        self['cryptsetup_key_types'][key_type] = config_dict


def _process_cryptsetup_multi(self, mapped_name, config):
    """
    Processes the cryptsetup configuration
    """
    self.logger.debug("[%s] Processing cryptsetup configuration: %s" % (mapped_name, config))
    for parameter in config:
        if parameter not in CRYPTSETUP_PARAMETERS:
            raise ValueError("Invalid parameter: %s" % parameter)

    if not config.get('partuuid') and not config.get('uuid'):
        raise ValueError("Unable to determine source device for: %s" % mapped_name)

    # Check if the key type is defined in the configuration, otherwise use the default, check if it's valud
    if key_type := config.get('key_type', self.get('key_type')):
        if key_type not in self['cryptsetup_key_types']:
            raise ValueError("Unknown key type: %s" % key_type)
        config['key_type'] = key_type

        # Inherit from the key type configuration
        for parameter in ['key_command', 'reset_command']:
            value = self['cryptsetup_key_types'][key_type].get(parameter)
            if parameter:
                config[parameter] = value.format(**config)

    if not config.get('retries'):
        self.logger.info("No retries specified, using default: %s" % self['cryptsetup_retries'])
        config['retries'] = self['cryptsetup_retries']

    self['cryptsetup'][mapped_name] = config


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
        if 'partuuid' in parameters:
            blkid_command = f"export CRYPTSETUP_SOURCE_{name}=$(blkid --match-token PARTUUID='{parameters['partuuid']}' --match-tag PARTUUID --output device)"
        elif 'uuid' in parameters:
            blkid_command = f"export CRYPTSETUP_SOURCE_{name}=$(blkid --match-token UUID='{parameters['uuid']}' --match-tag PARTUUID --output device)"
        else:
            raise ValueError("Unable to determine source device for %s" % name)

        check_command = f'if [ -z "$CRYPTSETUP_SOURCE_{name}" ]; then echo "Unable to resolve device source for {name}"; bash; else echo "Resolved device source: $CRYPTSETUP_SOURCE_{name}"; fi'
        out += [f"\necho 'Attempting to get device path for {name}'", blkid_command, check_command]

    return out


def open_crypt_key(self, name, parameters):
    """
    Returns bash lines to open a luks key and output it to specified key file
    """
    key_name = f"/run/key_{name}"

    out = [f"    echo 'Attempting to open luks key for {name}'"]
    out += [f"    {parameters['key_command']} {key_name}"]

    return out, key_name


def open_crypt_device(self, name, parameters):
    """
    Returns a bash script to open a cryptsetup device
    """
    self.logger.debug("[%s] Processing cryptsetup volume: %s" % (name, parameters))
    retries = parameters['retries']

    out = [f"echo 'Attempting to unlock device: {name}'"]
    out += [f"for ((i = 1; i <= {retries}; i++)); do"]

    # When there is a key command, read from the named pipe and use that as the key
    if 'key_command' in parameters:
        self.logger.debug("[%s] Using key command: %s" % (name, parameters['key_command']))
        out_line, key_name = open_crypt_key(self, name, parameters)
        out += out_line
        cryptsetup_command = f'    cryptsetup open --key-file {key_name}'
    elif 'key_file' in parameters:
        self.logger.debug("[%s] Using key file: %s" % (name, parameters['key_file']))
        cryptsetup_command = f'    cryptsetup open --key-file {parameters["key_file"]}'
    else:
        # Set tries to 1 since it runs in the loop
        cryptsetup_command = '    cryptsetup open --tries 1'

    # Add the header file if it exists
    if header_file := parameters.get('header_file'):
        out += [f"    echo 'Using header file: {header_file}'"]
        cryptsetup_command += f' --header {header_file}'

    # Add the variable for the source device and mapped name
    cryptsetup_command += f' $CRYPTSETUP_SOURCE_{name} {name}'
    out += [cryptsetup_command]

    # Check if the device was successfully opened
    out += ['    if [ $? -eq 0 ]; then',
            f'        echo "Successfully opened device: {name}"',
            '       break',
            '    else',
            f'        echo "Failed to open device: {name} ($i / {retries})"']
    # Add the reset command if it exists
    if reset_command := parameters.get('reset_command'):
        out += ['        echo "Running key reset command"',
                f'        {reset_command}']
    out += ['    fi']
    out += ['done']

    return out


def crypt_init(self):
    """
    Generates the bash script portion to prompt for keys
    """
    out = [r'echo -e "\n\n\nPress enter to start drive decryption.\n\n\n"', "read -sr"]
    for name, parameters in self.config_dict['cryptsetup'].items():
        out += open_crypt_device(self, name, parameters)
        if 'try_nokey' in parameters and parameters.get('key_file'):
            new_params = parameters.copy()
            for parameter in ['key_file', 'key_command', 'reset_command']:
                try:
                    new_params.pop(parameter)
                except KeyError:
                    pass
            out += [f'\ncryptsetup status {name}',
                    'if [ $? -ne 0 ]; then',
                    f'    echo "Failed to open device using keys: {name}"']
            out += [f'    {bash_line}' for bash_line in open_crypt_device(self, name, new_params)]
            out += ['fi']
    return out


def find_libgcc(self):
    """
    Finds libgcc.so, adds a copies item for it.
    """
    ldconfig = self._run(['ldconfig', '-p']).stdout.decode().split("\n")
    libgcc = [lib for lib in ldconfig if 'libgcc_s' in lib and 'libc6,x86-64' in lib][0]
    source_path = libgcc.partition('=> ')[-1]
    self.logger.debug("Source path for libgcc_s: %s" % source_path)

    self.config_dict['copies']['libgcc_s'] = {'source': source_path, 'destination': '/lib64/'}
