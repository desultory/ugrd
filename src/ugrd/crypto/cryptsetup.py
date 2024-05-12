__author__ = 'desultory'
__version__ = '1.5.1'

from zenlib.util import check_dict


_module_name = 'ugrd.crypto.cryptsetup'

CRYPTSETUP_PARAMETERS = ['key_type', 'partuuid', 'uuid', 'path', 'key_file', 'header_file', 'retries', 'key_command', 'reset_command', 'try_nokey']


@check_dict('cryptsetup', value_arg=1, return_arg=2, contains=True)  # Check if the mapped name is defined
def _merge_cryptsetup(self, mapped_name: str, config: dict) -> None:
    """ Merges the cryptsetup configuration """
    self.logger.log(5, "Existing cryptsetup configuration: %s" % self['cryptsetup'][mapped_name])
    self.logger.debug("[%s] Merging cryptsetup configuration: %s" % (mapped_name, config))
    return dict(self['cryptsetup'][mapped_name], **config)


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
    """ Returns the device path for a given a token, using the blkid command """
    from subprocess import run

    token_str = f"{token[0]}={token[1]}"
    self.logger.debug("Attempting to resolve device path using token: %s" % token_str)

    cmd = run(['blkid', '--match-token', token_str, '--output', 'device'], capture_output=True)
    if cmd.returncode != 0:
        self.logger.warning("If building for another system, validation must be disabled.")
        raise ValueError("Unable to resolve device path using token: %s" % token_str)

    device_path = cmd.stdout.decode().strip()
    self.logger.debug("Resolved device path: %s" % device_path)
    return device_path


def _validate_cryptsetup_config(self, mapped_name: str, config: dict) -> None:
    self.logger.log(5, "[%s] Validating cryptsetup configuration: %s" % (mapped_name, config))
    for parameter in config:
        if parameter not in CRYPTSETUP_PARAMETERS:
            raise ValueError("Invalid parameter: %s" % parameter)

    # The partuuid must be specified if using a detached header
    if config.get('header_file') and (not config.get('partuuid') and not config.get('path')):
        self.logger.warning("A partuuid or device path must be specified when using detached headers: %s" % mapped_name)
        if config.get('uuid'):
            raise ValueError("A UUID cannot be used with a detached header: %s" % mapped_name)
    elif not any([config.get('partuuid'), config.get('uuid'), config.get('path')]):
        self.logger.warning("A device uuid, partuuid, or path must be specified for cryptsetup mount: %s" % mapped_name)


def _process_cryptsetup_multi(self, mapped_name: str, config: dict) -> None:
    """ Processes the cryptsetup configuration """
    config = _merge_cryptsetup(self, mapped_name, config)  # Merge the config with the existing configuration
    _validate_cryptsetup_config(self, mapped_name, config)  # Validate the configuration
    self.logger.debug("[%s] Processing cryptsetup configuration: %s" % (mapped_name, config))
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
    for name, parameters in self['cryptsetup'].items():
        if parameters.get('path') and not self['validate']:
            self.logger.warning("Using device paths is unreliable and can result in boot failures.")
            out += [f"export CRYPTSETUP_SOURCE_{name}={parameters.get('path')}"]
        elif not parameters.get('partuuid') and not parameters.get('uuid') and parameters.get('path'):
            raise ValueError("Validation must be disabled to use device paths with the cryptsetup module.")
        else:
            try:
                token = ('PARTUUID', parameters['partuuid']) if parameters.get('partuuid') else ('UUID', parameters['uuid'])
            except KeyError:
                raise ValueError("A partuuid or uuid must be specified for cryptsetup mount: %s" % name)
            self.logger.debug("[%s] Created block device identifier token: %s" % (name, token))
            parameters['_host_device_path'] = _get_device_path_from_token(self, token)
            # Add a blkid command to get the source device in the initramfs, only match if the device has a partuuid
            out.append(f"export SOURCE_TOKEN_{name}='{token[0]}={token[1]}'")
            source_cmd = f'export CRYPTSETUP_SOURCE_{name}=$(blkid --match-token "$SOURCE_TOKEN_{name}" --match-tag PARTUUID --output device)'

            check_command = [f'if [ -z "$CRYPTSETUP_SOURCE_{name}" ]; then',
                             f'    echo "Unable to resolve device source for {name}"',
                             '    _mount_fail',
                             'else',
                             f'    echo "Resolved device source: $CRYPTSETUP_SOURCE_{name}"',
                             'fi']

            out += [f"echo 'Attempting to get device path for {name}'", source_cmd, *check_command]
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
    """ Returns a bash script to open a cryptsetup device. """
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

    if self['cryptsetup_trim']:
        cryptsetup_command += ' --allow-discards'
        self.logger.warning("Using --allow-discards can be a security risk.")

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
    if not self['cryptsetup_autoretry']:
        out += ['        read -sr -p "Press enter to retry"']
    # Add the reset command if it exists
    if reset_command := parameters.get('reset_command'):
        out += ['        echo "Running key reset command"',
                f'        {reset_command}']
    out += ['    fi']
    out += ['done\n']

    return out


def crypt_init(self) -> list[str]:
    """ Generates the bash script portion to prompt for keys. """
    out = [r'echo "Unlocking LUKS volumes, module version: %s"' % __version__,]
    for name, parameters in self['cryptsetup'].items():
        # Check if the volume is already open, if so, skip it
        out += [f'cryptsetup status {name} > /dev/null 2>&1',
                'if [ $? -eq 0 ]; then',
                f'    echo "Device already open: {name}"',
                '    return',
                'else'
                f'    echo -e "\\n\\nPress enter to unlock device: {name}\\n\\n"',
                '    read -sr',
                'fi']
        out += open_crypt_device(self, name, parameters)
        if 'try_nokey' in parameters and parameters.get('key_file'):
            new_params = parameters.copy()
            for parameter in ['key_file', 'key_command', 'reset_command']:
                try:
                    new_params.pop(parameter)
                except KeyError:
                    pass
            out += [f'cryptsetup status {name}',
                    'if [ $? -ne 0 ]; then',
                    f'    echo "Failed to open device using keys: {name}"']
            out += [f'    {bash_line}' for bash_line in open_crypt_device(self, name, new_params)]
            out += ['fi']
    return out


def find_libgcc(self) -> None:
    """
    Finds libgcc.so, adds a 'dependencies' item for it.
    Adds the parent directory to 'library_paths'
    """
    from pathlib import Path

    ldconfig = self._run(['ldconfig', '-p']).stdout.decode().split("\n")
    libgcc = [lib for lib in ldconfig if 'libgcc_s' in lib and 'libc6,x86-64' in lib][0]
    source_path = Path(libgcc.partition('=> ')[-1])
    self.logger.info("Source path for libgcc_s: %s" % source_path)

    self['dependencies'] = source_path
    self['library_paths'] = str(source_path.parent)
