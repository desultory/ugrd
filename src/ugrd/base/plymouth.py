from zenlib.util import unset
from pathlib import Path


PLYMOUTH_CONFIG_FILES = ['/etc/plymouth//plymouthd.conf', '/usr/share/plymouth/plymouthd.defaults']


@unset('plymouth_config')
def find_plymouth_config(self):
    """ Adds the plymouth config files to the build directory """
    self.logger.info("Finding plymouthd.conf")
    for file in PLYMOUTH_CONFIG_FILES:
        if Path(file).exists():
            self['plymouth_config'] = file
            break
    else:
        raise FileNotFoundError('Failed to find plymouthd.conf')


def _process_plymouth_config(self, file):
    """ Checks that the config file is valid """
    plymouth_config = Path(file)
    if not plymouth_config.exists():
        raise FileNotFoundError('Specified plymouthd.conf does not exist: %s' % file)
    self.logger.info("Processing plymouthd.conf: %s" % plymouth_config)

    with open(file, 'r') as f:
        for line in f.readlines():
            if line.startswith('Theme'):
                theme = line.split('=')[1].strip()
                if self['plymouth_theme'] and theme != self['plymouth_theme']:
                    self.logger.warning("Configured plymouth theme does not match the one in plymouthd.conf")
                else:
                    self.logger.info("Found plymouth theme: %s" % theme)
                    self['plymouth_theme'] = theme
                break
        else:
            raise ValueError('Failed to find Theme in plymouthd.conf')
    dict.__setitem__(self, 'plymouth_config', plymouth_config)
    self['dependencies'] = plymouth_config


def start_plymouth(self):
    """
    Runs plymouthd
    """
    return ['plymouthd --attach-to-session --pid-file /run/plymouth/pid --mode=boot', 'plymouth show-splash']
