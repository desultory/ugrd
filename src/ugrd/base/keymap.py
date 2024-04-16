__author__ = 'desultory'
__version__ = '0.1.0'

from zenlib.util import check_dict


def _process_keymap_file(self, keymap_file: str) -> str:
    """ Sets the keymap file, adding it to the list of files to be copied to the new root. """
    dict.__setitem__(self, 'keymap_file', keymap_file)
    self['dependencies'] = keymap_file


@check_dict('keymap_file', raise_exception=True, message="keymap_file must be set to use the keymap module")
def set_keymap(self) -> str:
    """ Sets the specified keymap. """
    return [f'echo "Setting keymap: {self["keymap_file"]}"',
            f'loadkeys {self["keymap_file"]}']

