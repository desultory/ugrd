__author__ = 'desultory'
__version__ = '1.1.1'


def switch_root(self) -> str:
    """
    Should be the final statement, switches root
    """
    return f"exec switch_root {self.config_dict['mounts']['root']['destination']} /sbin/init"

