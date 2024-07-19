__author__ = 'desultory'
__version__ = '2.4.3'

from zenlib.util import check_dict


_module_name = 'ugrd.crypto.cryptsetup'

CRYPTSETUP_PARAMETERS = ['key_type', 'partuuid', 'uuid', 'path', 'key_file', 'header_file', 'retries', 'key_command', 'reset_command', 'try_nokey', 'include_key']


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


@check_dict('cryptsetup_keyfile_validation', value=True, log_level=30, message="Skipping cryptsetup keyfile validation.")
@check_dict('validate', value=True, log_level=30, message="Skipping cryptsetup key validation.")
def _validate_crypysetup_key(self, key_paramters: dict) -> None:
    """ Validates the cryptsetup key """
    if key_paramters.get('include_key'):
        self.logger.info("Skipping key validation for included key.")
        return

    from pathlib import Path
    key_path = Path(key_paramters['key_file'])

    if not key_path.is_file():
        raise FileNotFoundError("Key file not found: %s" % key_path)

    key_copy = key_path
    while parent := key_copy.parent:
        if parent == Path('/'):
            raise ValueError("No mount is defined for external key file: %s" % key_path)
        if str(parent).lstrip('/') in self['mounts']:
            self.logger.debug("Found mount for key file: %s" % parent)
            break
        key_copy = parent


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
        if not self['autodetect_root_luks']:
            raise ValueError("A device uuid, partuuid, or path must be specified for cryptsetup mount: %s" % mapped_name)

    if config.get('key_file'):
        _validate_crypysetup_key(self, config)


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

    # Include the key file if include_key is set
    if config.get('include_key'):
        self['dependencies'] = config['key_file']

    if not config.get('retries'):
        self.logger.info("[%s:%s] No retries specified, using default: %s" % (_module_name, mapped_name, self['cryptsetup_retries']))
        config['retries'] = self['cryptsetup_retries']

    self['cryptsetup'][mapped_name] = config


@check_dict('validate', value=True, log_level=30, message="Skipping LUKS source validation.")
def _validate_luks_source(self, mapped_name: str) -> None:
    """ Checks that a LUKS source device is valid """
    for _dm_info in self['_dm_info'].values():
        if _dm_info['name'] == mapped_name:
            dm_info = _dm_info
            break
    else:
        raise ValueError("No device mapper information found for: %s" % mapped_name)

    cryptsetup_info = self['cryptsetup'][mapped_name]

    if not dm_info['uuid'].startswith('CRYPT-LUKS'):
        raise ValueError("Device is not a crypt device: %s" % dm_info)

    slave_source = dm_info['slaves'][0]

    try:
        blkid_info = self['_blkid_info'][f'/dev/{slave_source}']
    except KeyError:
        blkid_info = self['_blkid_info'][f'/dev/mapper/{slave_source}']

    for token_type in ['partuuid', 'uuid']:
        if cryptsetup_token := cryptsetup_info.get(token_type):
            if blkid_info.get(token_type) != cryptsetup_token:
                raise ValueError("[%s] LUKS %s mismatch, found '%s', expected: %s" %
                                 (mapped_name, token_type, cryptsetup_token, blkid_info[token_type]))
            break
    else:
        raise ValueError("[%s] Unable to validate LUKS source: %s" % (mapped_name, cryptsetup_info))


def export_crypt_sources(self) -> list[str]:
    """
    Validates the cryptsetup configuration.
    Adds the cryptsetup source and token to the exports.
    Sets the token to the partuuid or uuid if it exists.
    Sets the SOURCE when using a path.
    Only allows using the path if validation is disabled.
    """
    for name, parameters in self['cryptsetup'].items():
        _validate_luks_source(self, name)
        if parameters.get('path'):
            if not self['validate']:
                self.logger.warning("Using device paths is unreliable and can result in boot failures. Consider using partuuid.")
                self['exports']['CRYPTSETUP_SOURCE_%s' % name] = parameters['path']
                self.logger.info("Set CRYPTSETUP_SOURCE_%s: %s" % (name, parameters.get('path')))
                continue
            raise ValueError("Validation must be disabled to use device paths with the cryptsetup module.")
        elif not parameters.get('partuuid') and not parameters.get('uuid') and parameters.get('path'):
            raise ValueError("Device source for cryptsetup mount must be specified: %s" % name)

        for token_type in ['partuuid', 'uuid']:
            if token := parameters.get(token_type):
                self['exports']['CRYPTSETUP_TOKEN_%s' % name] = f"{token_type.upper()}={token}"
                self.logger.debug("Set CRYPTSETUP_TOKEN_%s: %s=%s" % (name, token_type.upper(), token))
                break
        else:
            raise ValueError("A partuuid or uuid must be specified for cryptsetup mount: %s" % name)


def get_crypt_dev(self) -> list[str]:
    """
    Gets the device path for a particular cryptsetup device at runtime.
    First attempts to read CRYPTSETUP_SOURCE_{name} if it exists.
    If it doesn't exist, or the device is not found, it will attempt to resolve the device using the token.
    If that doesn't exist, it will fail.
    """
    return ['source_dev="$(readvar CRYPTSETUP_SOURCE_"$1")"',
            'source_token="$(readvar CRYPTSETUP_TOKEN_"$1")"',
            'if [ -n "$source_dev" ]; then',
            '    if [ -e "$source_dev" ]; then',
            '        echo -n "$source_dev"',
            '        return',
            '    fi',
            'fi',
            'if [ -n "$source_token" ]; then',
            '    source_dev=$(blkid --match-token "$source_token" --output device)',
            '    if [ -n "$source_dev" ]; then',
            '        echo -n "$source_dev"',
            '        return',
            '    fi',
            'fi',
            'rd_fail "Failed to resolve device source for cryptsetup mount: $1"']


def open_crypt_device(self, name: str, parameters: dict) -> list[str]:
    """ Returns a bash script to open a cryptsetup device. """
    self.logger.debug("[%s] Processing cryptsetup volume: %s" % (name, parameters))
    retries = parameters['retries']

    out = [f"prompt_user 'Press enter to unlock device: {name}'"] if self['cryptsetup_prompt'] else []
    out += [f"for ((i = 1; i <= {retries}; i++)); do"]

    # When there is a key command, read from the named pipe and use that as the key
    if 'key_command' in parameters:
        self.logger.debug("[%s] Using key command: %s" % (name, parameters['key_command']))
        out += [f"    einfo 'Attempting to open LUKS key: {parameters['key_file']}'",
                f"    edebug 'Using key command: {parameters['key_command']}'"]
        cryptsetup_command = f'{parameters["key_command"]} | cryptsetup open --key-file -'
    elif 'key_file' in parameters:
        self.logger.debug("[%s] Using key file: %s" % (name, parameters['key_file']))
        cryptsetup_command = f'cryptsetup open --key-file {parameters["key_file"]}'
    else:
        # Set tries to 1 since it runs in the loop
        cryptsetup_command = 'cryptsetup open --tries 1'

    # Add the header file if it exists
    if header_file := parameters.get('header_file'):
        out += [f"    einfo 'Using header file: {header_file}'"]
        cryptsetup_command += f' --header {header_file}'

    if self['cryptsetup_trim']:
        cryptsetup_command += ' --allow-discards'
        self.logger.warning("Using --allow-discards can be a security risk.")

    # Add the variable for the source device and mapped name
    cryptsetup_command += f' "$(get_crypt_dev {name})" {name}'

    # Check if the device was successfully opened
    out += [f'    if {cryptsetup_command}; then',
            f'        einfo "Successfully opened device: {name}"',
            '        break',
            '    else',
            f'        ewarn "Failed to open device: {name} ($i / {retries})"']
    # Halt if the autoretry is disabled
    if not self['cryptsetup_autoretry']:
        out += ['        prompt_user "Press enter to retry"']
    # Add the reset command if it exists
    if reset_command := parameters.get('reset_command'):
        out += ['        einfo "Running key reset command"',
                f'        {reset_command}']
    out += ['    fi']
    out += ['done\n']

    return out


def crypt_init(self) -> list[str]:
    """ Generates the bash script portion to prompt for keys. """
    out = [r'einfo "Unlocking LUKS volumes, ugrd.cryptsetup version: %s"' % __version__]
    for name, parameters in self['cryptsetup'].items():
        # Check if the volume is already open, if so, skip it
        out += [f'if cryptsetup status {name} > /dev/null 2>&1; then',
                f'    ewarn "Device already open: {name}"',
                '    return',
                'fi']
        out += open_crypt_device(self, name, parameters)
        if 'try_nokey' in parameters and parameters.get('key_file'):
            new_params = parameters.copy()
            for parameter in ['key_file', 'key_command', 'reset_command']:
                try:
                    new_params.pop(parameter)
                except KeyError:
                    pass
            out += [f'if ! cryptsetup status {name} > /dev/null 2>&1; then',
                    f'    ewarn "Failed to open device using keys: {name}"']
            out += [f'    {bash_line}' for bash_line in open_crypt_device(self, name, new_params)]
            out += ['fi']
        # Check that the device was successfully opened
        out += [f'if ! cryptsetup status {name} > /dev/null 2>&1; then',
                f'    rd_fail "Failed to open cryptsetup device: {name}"',
                'fi']
    return out

