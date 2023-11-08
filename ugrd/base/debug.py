__author__ = "desultory"
__version__ = "0.1.0"

from pathlib import Path


def start_shell(self):
    """
    Start a bash shell at the start of the initramfs.
    """
    if self.config_dict["start_shell"]:
        return "bash"
    else:
        return None


def pull_python_parts(self):
    """
    Gets stuff from /usr/lib/python-exec/python{version} and adds it to the dependencies.
    """
    pyton_parts = ['python', 'python3', 'python-config', 'pydoc']
    for part in pyton_parts:
        self.config_dict['dependencies'] = Path(f"/usr/lib/python-exec/python{self.config_dict['python_version']}") / part


def pull_valgrind_parts(self):
    """
    Gets the stuff which was dostrip -x'd from valgrind and adds it to the dependencies.
    """
    for file in Path('/usr/lib64/valgrind').glob('*.a'):
        self.logger.debug("Found valgrind dependency: %s", file)
        self.config_dict['dependencies'] = file
