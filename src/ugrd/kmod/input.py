__version__ = "0.2.0"

from pathlib import Path

from zenlib.util import colorize as c_
from zenlib.util import contains


def _count_bits(hex_str):
    """Counts the number of bits set in a hexadecimal string."""
    count = 0
    for char in hex_str:
        try:
            count += bin(int(char, 16)).count("1")
        except ValueError:
            # Handle non-hexadecimal characters
            pass
    return count


@contains("kmod_autodetect_input")
def autodetect_input(self):
    """Looks through /sys/class/input/input*/capabilities/,
    looks for the "key" capability, checks how many keys are defined.
    If more than keyboard_key_threshold keys are defined, it assumes that the device is a keyboard.
    adds the resolved path of device/driver to _kmod_auto.

    If the input device path has "/usb" in it, enable the ugrd.kmod.usb module.
    """
    found_keyboard = False
    for input_dev in Path("/sys/class/input").glob("input*"):
        key_cap_path = input_dev / "capabilities" / "key"
        if key_cap_path.exists():
            keyboard_name = (input_dev / "name").read_text().strip()
            enabled_keys = _count_bits(key_cap_path.read_text().splitlines()[0].strip())
            if enabled_keys < self.keyboard_key_threshold:
                self.logger.debug(
                    f"[{input_dev.name}:{c_(keyboard_name, 'blue')}] Not enough keys detected: {c_(enabled_keys, 'yellow')} < {self.keyboard_key_threshold}"
                )
                continue
            keyboard_driver = (input_dev / "device" / "driver").resolve().name
            self.logger.info(f"[{c_(keyboard_name, 'blue')}] Detected driver: {c_(keyboard_driver, 'cyan')}")
            self._kmod_auto = [keyboard_driver]
            found_keyboard = True

            if "ugrd.kmod.usb" in self["modules"]:
                continue

            # Check for USB devices if the USB module is not already enabled
            for part in input_dev.parts:
                if part.startswith("usb") and "ugrd.kmod.usb" not in self["modules"]:
                    self.logger.info(f"Detected USB device, enabling ugrd.kmod.usb: {c_(input_dev.name, 'cyan')}")
                    self["modules"] = "ugrd.kmod.usb"
                    break

    # Maybe raise an exception once detection is more well tested
    if not found_keyboard:
        self.logger.warning(f"Unable to detect a keyboard with keyboard_key_threshold is set to: {c_(self.keyboard_key_threshold, 'yellow')}")
