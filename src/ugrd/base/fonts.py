__version__ = "0.1.0"

from pathlib import Path
from subprocess import run

from ugrd.exceptions import AutodetectError, ValidationError
from zenlib.util import colorize as c_

STYLE_SPECIFIERS = ["bold", "light", "italic", "regular", "medium", "thin"]


def _strip_font_size(self, font_name: str) -> str:
    """Removes trailing numbers after a space (e.g., 'FontName 12')"""
    if " " in font_name and font_name.split(" ")[-1].isdigit():
        self.logger.debug(f"Stripping font size from font name: {c_(font_name, 'yellow')}")
        return font_name.rsplit(" ", 1)[0]
    return font_name


def _strip_font_type(self, font_name: str) -> str:
    """Removes style specifiers from font name (e.g., 'FontName Bold Italic')"""
    parts = font_name.split(" ")
    filtered_parts = [part for part in parts if part.lower() not in STYLE_SPECIFIERS]
    if len(parts) != len(filtered_parts):
        self.logger.debug(f"Stripping style specifiers from font name: {c_(font_name, 'yellow')}")
    return " ".join(filtered_parts)


def _get_font_name(self, font_name: str) -> str:
    """Given a font name, returns the name from fc-match output.
    The output is in the format:
        fontfile.ext: "Font name" "Style" ...
    """
    r = run(["fc-match", font_name], capture_output=True, text=True)

    if r.returncode != 0:
        if font_name:
            raise AutodetectError("Could not find a default font using fc-match.")
        raise ValidationError(f"Font could not be found: {c_(font_name, 'red')}")

    # Split after the colon, then get the first part and remove quotes
    matched_name = r.stdout.split(":")[1].split('" "')[0].strip('" ')
    return matched_name


def _get_font_path(self, font_name: str) -> Path:
    """Uses fc-match -f '%{file}' to find the font file path."""
    r = run(["fc-match", "-f", "%{file}", font_name], capture_output=True, text=True)
    font_path = Path(r.stdout.strip())
    return font_path


def _process_default_font(self, font_name: str) -> None:
    """Sets the default font, tries adding it to fonts first"""
    self.logger.info(f"Setting default font to: {c_(font_name, 'cyan')}")
    self.data["default_font"] = font_name
    self["fonts"] = font_name


def _process_fonts_multi(self, font_name: str) -> None:
    """Checks that the font is valid, removes trailing numbers after a space (e.g., 'FontName 12')
    uses fc-match -f '%{file}' to find the font file path, appends it to self["dependencies"] if valid.

    Sets the default font if it's not already set.
    """

    if not self["default_font"]:
        default_font_name = _get_font_name(self, "")
        self["default_font"] = default_font_name

    cleaned_font_name = _strip_font_size(self, font_name)
    # If the cleaned font name returns the default font, it is not found
    if cleaned_font_name == self["default_font"]:
        # The default font is being set, so we assume it's valid
        pass
    elif _get_font_name(self, cleaned_font_name) == self["default_font"]:
        self.logger.debug(
            f"Font lookup returned default font, trying to strip style specifiers: {c_(cleaned_font_name, 'yellow')}"
        )
        cleaned_font_name = _strip_font_type(self, cleaned_font_name)
        if _get_font_name(self, cleaned_font_name) == self["default_font"]:
            raise ValidationError(f"Font could not be found: {c_(font_name, 'red')}")

    if font_path := _get_font_path(self, cleaned_font_name):
        self.data["fonts"][font_name] = font_path
        self["dependencies"] = font_path
    else:
        raise ValidationError(f"Font could not be found: {c_(font_name, 'red')}")
