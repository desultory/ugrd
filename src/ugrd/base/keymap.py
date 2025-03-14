__author__ = "desultory"
__version__ = "1.0.1"

from pathlib import Path

from zenlib.util import contains


def _find_keymap_include(self, base_path, included_file, no_recurse=False) -> str:
    """Finds the included file in the keymap file.
    This function recursively searches for the included file based on the base path.
    If the base path is not a directory, uses the parent directory.
    When not found, searches the 'include' directory, if in the parent directory.
    Stopping at the 'keymaps' directory, if not found, recursively searches the parent directory.
    Keeps recursively searching if the included file does not end with '.inc'.
    """

    if not isinstance(base_path, Path):
        base_path = Path(base_path)
    if not base_path.is_dir():
        base_path = base_path.parent
    self.logger.debug("Searching for included file '%s' in dir: %s" % (included_file, base_path))

    for file in base_path.iterdir():
        if file.name == included_file:
            return str(file)
        if file.name == included_file + ".gz":
            return str(file)

    self.logger.debug("Could not find included file '%s' in dir: %s" % (included_file, base_path))

    if base_path.name != "include":
        include_dir = base_path / "include"
        if include_dir.exists():
            self.logger.debug("Searching include directory: %s" % include_dir)
            try:
                return _find_keymap_include(self, include_dir, included_file, no_recurse=True)
            except FileNotFoundError:
                pass

    if base_path.name != "keymaps" and not no_recurse:
        self.logger.debug("Searching parent directory: %s" % base_path.parent)
        return _find_keymap_include(self, base_path.parent, included_file)

    if not included_file.endswith(".inc"):
        try:
            return _find_keymap_include(self, base_path, included_file + ".inc")
        except FileNotFoundError:
            pass

    raise FileNotFoundError(f"Could not find included file: {included_file}")


def _add_keymap_file(self, keymap_file: str) -> None:
    """Adds an individual keymap file, handling gzipped files."""
    if keymap_file.endswith(".gz"):
        self["gz_dependencies"] = keymap_file
        import gzip

        with gzip.open(keymap_file, "rb") as f:
            keymap_data = f.read()
            keymap_file = keymap_file[:-3]
    else:  # Add the keymap file as a dependency, reading the data
        self["dependencies"] = keymap_file
        keymap_data = open(keymap_file, "rb").read()

    keymap_data = keymap_data.decode(errors="ignore")

    for line in keymap_data.splitlines():
        if line.startswith("include"):  # Handle keymap includes
            include_name = line.split()[1].replace('"', "")
            include_file = _find_keymap_include(self, keymap_file, include_name)
            self.logger.info("Detected keymap include, adding file: %s" % include_file)
            _add_keymap_file(self, include_file)


def _process_keymap_file(self, keymap_file: str) -> None:
    """Sets the keymap file, adding it to the list of files to be copied to the new root."""
    _add_keymap_file(self, keymap_file)
    self.data["keymap_file"] = keymap_file.replace(".gz", "")  # GZipped files are decompressed before copying


@contains("keymap_file", "keymap_file must be set to use the keymap module", raise_exception=True)
def set_keymap(self) -> str:
    """Sets the specified keymap."""
    return f"""
    einfo "Setting keymap: {self["keymap_file"]}"
    loadkeys {self["keymap_file"]}
    """
