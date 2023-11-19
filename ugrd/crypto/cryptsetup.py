__author__ = 'desultory'
__version__ = '1.0.0'

_module_name = 'ugrd.crypto.cryptsetup'

CRYPTSETUP_PARAMETERS = ['key_type', 'partuuid', 'uuid', 'key_file', 'header_file', 'retries', 'key_command', 'reset_command', 'try_nokey']


def _process_cryptsetup_key_types_multi(self, key_type: str, config: dict) -> None:
    """
    Processes the cryptsetup key types.
    Updates the key type configuration if it already exists, otherwise creates a new key type.
    """
    self.logger.debug("[%s] Processing cryptsetup key type configuration: %s" % (key_type, config))
    for parameter in config:
        if parameter not in CRYPTSETUP_PARAMETERS:
            raise ValueError("Invalid parameter: %s" % parameter)

    # Update the key if it already exists, otherwise create a new key type
    if key_type in self['cryptsetup_key_types']:
        self.logger.debug("[%s] Updating key type configuration: %s" % (key_type, config))
        self['cryptsetup_key_types'][key_type].update(config)
    else:
        # Make sure the key type has a key command
        if 'key_command' not in config:
            raise ValueError("Missing key_command for key type: %s" % key_type)
        self['cryptsetup_key_types'][key_type] = config


def _get_device_path_from_token(self, token: tuple[str, str]) -> str:
    """
    Returns the device path for a given a token, using the blkid command
    """
    from subprocess import run

    token_str = f"{token[0]}={token[1]}"
    self.logger.debug("Attempting to resolve device path using token: %s" % token_str)

    cmd = run(['blkid', '--match-token', token_str, '--output', 'device'], capture_output=True)
    if cmd.returncode != 0:
        self.logger.warning("If building for another system, hostonly mode must be disabled.")
        raise ValueError("Unable to resolve device path using token: %s" % token_str)

    device_path = cmd.stdout.decode().strip()
    self.logger.debug("Resolved device path: %s" % device_path)
    return device_path


def _process_cryptsetup_multi(self, mapped_name: str, config: dict) -> None:
    """
    Processes the cryptsetup configuration
    """
    self.logger.debug("[%s] Processing cryptsetup configuration: %s" % (mapped_name, config))
    for parameter in config:
        if parameter not in CRYPTSETUP_PARAMETERS:
            raise ValueError("Invalid parameter: %s" % parameter)

    # The partuuid must be specified if using a detached header
    if config.get('header_file') and not config.get('partuuid'):
        raise ValueError("A partuuid must be specified when using detached headers: %s" % mapped_name)
    elif not config.get('partuuid') and not config.get('uuid'):
        raise ValueError("Either a uuid or partuuid must be specified with cryptsetup mounts: %s" % mapped_name)

    # If using hostonly mode, check that the mount source exists
    if self['hostonly']:
        # Set it to _host_device_path just to appear in the configuration, it is not used
        if config.get('partuuid'):
            config['_host_device_path'] = _get_device_path_from_token(self, ('PARTUUID', config['partuuid']))
        elif config.get('uuid'):
            config['_host_device_path'] = _get_device_path_from_token(self, ('UUID', config['uuid']))

    # Check if the key type is defined in the configuration, otherwise use the default, check if it's valid
    if key_type := config.get('key_type', self.get('cryptsetup_key_type')):
        self.logger.debug("[%s] Using key type: %s" % (mapped_name, key_type))
        if key_type not in self['cryptsetup_key_types']:
            raise ValueError("Unknown key type: %s" % key_type)
        config['key_type'] = key_type

        # Inherit from the key type configuration
        for parameter in ['key_command', 'reset_command']:
            if value := self['cryptsetup_key_types'][key_type].get(parameter):
                config[parameter] = value.format(**config)

    if not config.get('retries'):
        self.logger.info("[%s] No retries specified, using default: %s" % (_module_name, self['cryptsetup_retries']))
        config['retries'] = self['cryptsetup_retries']

    self['cryptsetup'][mapped_name] = config


def get_crypt_sources(self) -> list[str]:
    """
    Goes through each cryptsetup device
    Creates a bash command to get the source device
    Exports the command as an environment variable in the format:
        CRYPTSETUP_SOURCE_{name}=`device`
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


def open_crypt_key(self, name: str, parameters: dict) -> tuple[list[str], str]:
    """
    Returns a tuple of bash lines and the path to the key file
    Returns bash lines to open a luks key and output it to specified key file
    """
    key_path = f"/run/key_{name}"

    out = [f"    echo 'Attempting to open luks key for {name}'"]
    out += [f"    {parameters['key_command']} {key_path}"]

    return out, key_path


def open_crypt_device(self, name: str, parameters: dict) -> list[str]:
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
            '        break',
            '    else',
            f'        echo "Failed to open device: {name} ($i / {retries})"']
    # Halt if the autoretry is disabled
    if not self.config_dict['cryptsetup_autoretry']:
        out += ['        read -sr -p "Press enter to retry"']
    # Add the reset command if it exists
    if reset_command := parameters.get('reset_command'):
        out += ['        echo "Running key reset command"',
                f'        {reset_command}']
    out += ['    fi']
    out += ['done']

    return out


def crypt_init(self) -> list[str]:
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


def find_libgcc(self) -> None:
    """
    Finds libgcc.so, adds a 'dependencies' item for it.
    Adds the parend directory to 'library_paths'
    """
    from pathlib import Path

    ldconfig = self._run(['ldconfig', '-p']).stdout.decode().split("\n")
    libgcc = [lib for lib in ldconfig if 'libgcc_s' in lib and 'libc6,x86-64' in lib][0]
    source_path = Path(libgcc.partition('=> ')[-1])
    self.logger.debug("Source path for libgcc_s: %s" % source_path)

    self.config_dict['dependencies'] = source_path
    self.config_dict['library_paths'] = str(source_path.parent)
