__author__ = "desultory"
__version__ = "0.1.2"

from pathlib import Path


def start_shell(self) -> str:
    """
    Start a bash shell at the start of the initramfs.
    """
    if self["start_shell"]:
        return "bash"


def pull_python_parts(self) -> None:
    """
    Gets stuff from /usr/lib/python-exec/python{version} and adds it to the dependencies.
    """
    pyton_parts = ['python', 'python3', 'python-config', 'pydoc']
    for part in pyton_parts:
        self['dependencies'] = Path(f"/usr/lib/python-exec/python{self['python_version']}") / part


def pull_valgrind_parts(self) -> None:
    """
    Gets the stuff which was dostrip -x'd from valgrind and adds it to the dependencies.
    """
    for file in Path('/usr/lib64/valgrind').glob('*.a'):
        self.logger.debug("Found valgrind dependency: %s", file)
        self['dependencies'] = file
