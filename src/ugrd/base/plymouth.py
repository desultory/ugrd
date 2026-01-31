__version__ = "0.5.0"

from configparser import ConfigParser
from pathlib import Path

from ugrd.exceptions import ValidationError
from zenlib.types import NoDupFlatList
from zenlib.util import colorize as c_

PLYMOUTH_CONFIG_FILES = ["/etc/plymouth/plymouthd.conf", "/usr/share/plymouth/plymouthd.defaults"]
PLYMOUTH_LIBRARIES = ["/usr/lib64/plymouth", "/usr/lib/plymouth"]


def find_plymouth_config(self) -> None:
    """Processes themes from plymouth config file
    Sets the config file if it is the first one found"""
    for file in PLYMOUTH_CONFIG_FILES:
        plymouth_config = ConfigParser()
        plymouth_config.read(file)
        if plymouth_config.has_section("Daemon") and plymouth_config.has_option("Daemon", "Theme"):
            self["plymouth_themes"] += plymouth_config["Daemon"]["Theme"]
            if str(self["plymouth_config"]) == ".":  # Set the first config file found
                self["plymouth_config"] = file
            continue
        self.logger.warning("Plymouth config file missing theme option: %s" % file)
    if not self["plymouth_themes"]:
        self.logger.error("No plymouth theme found in config files.")


def _process_plymouth_themes_multi(self, theme) -> None:
    """Checks that the theme is valid"""
    theme_dir = Path("/usr/share/plymouth/themes") / theme
    if not theme_dir.exists():
        raise FileNotFoundError("Theme directory not found: %s" % theme_dir)
    self.data["plymouth_themes"].append(theme)


def _get_plymouth_theme_fonts(self, theme_name: str) -> NoDupFlatList[Path]:
    """Reads Font and TitleFont from plymouth theme .plymouth files
    returns a list of paths for all fonts found
    """
    config_file = Path("/usr/share/plymouth/themes") / theme_name / f"{theme_name}.plymouth"
    theme_config = ConfigParser()
    theme_config.read(config_file)
    font_files = NoDupFlatList(logger=self.logger)

    for section in theme_config.sections():
        for key in ["Font", "TitleFont"]:
            if theme_config.has_option(section, key):
                font_files.append(theme_config[section][key])

    return font_files


def pull_plymouth(self) -> None:
    """Adds plymouth files to dependencies"""
    dir_list = [*PLYMOUTH_LIBRARIES]
    for theme in self["plymouth_themes"]:
        theme_path = Path("/usr/share/plymouth/themes/") / theme
        if not theme_path.exists():
            raise ValidationError(f"Plymouth theme not found: {c_(theme, 'red')}")

        if font_files := _get_plymouth_theme_fonts(self, theme):
            font_str = c_(", ".join(str(f) for f in font_files), "green")
            self.logger.info(f"[{c_(theme, 'blue')}] Adding plymouth theme fonts: {font_str}")
            self["fonts"] = font_files
        else:
            self.logger.info(f"[{c_(theme, 'yellow')}] No fonts found in plymouth theme.")

        dir_list.append(theme_path)

    for lib_dir in dir_list:
        if Path(lib_dir).exists():
            self.logger.debug(f"Adding plymouth files to dependencies: {lib_dir}")
            for file in Path(lib_dir).rglob("*"):
                if file.name.endswith(".so"):
                    self["libraries"] = file
                else:
                    self["dependencies"] = file

    if str(self["plymouth_config"]) != "/usr/share/plymouth/plymouthd.defaults":
        self["copies"] = {
            "plymouth_config_file": {"source": self["plymouth_config"], "destination": "/etc/plymouth/plymouthd.conf"}
        }
    self["libraries"] = "libdrm"


def _get_plymouthd_args(self) -> str:
    """Returns arguments for running plymouthd"""
    base_args = "--mode=boot --pid-file=/run/plymouth/plymouth.pid"
    cmdline_args = []
    if self["kmod_ignore_video"]:  # If the video mask is enabled, force plymouth.use-simpledrm option
        cmdline_args.append("plymouth.use-simpledrm")
    if self["plymouth_force_splash"]:
        base_args += " --splash"
    if self["plymouth_debug"]:
        base_args += " --debug --debug-file=/run/plymouth/plymouth.log"

    if cmdline_args:
        return f'{base_args} --kernel-command-line="{" ".join(cmdline_args)} $(cat /proc/cmdline)"'

    return base_args


def start_plymouth(self) -> str:
    """Returns shell lines to run plymouthd"""
    return f"""
    {"klog '[UGRD] Starting plymouthd'" if self["plymouth_debug"] else ""}
    plymouthd {_get_plymouthd_args(self)}
    if ! plymouth --ping; then
        eerror "Failed to start plymouthd"
        {"klog '[UGRD] Failed to start plymouthd'" if self["plymouth_debug"] else ""}
        return 1
    fi
    setvar plymouth 1
    plymouth show-splash
    """


def finish_plymouth(self) -> str:
    """Returns shell lines to stop plymouthd
    verifies that plymouthd stopped successfully
    f"""
    if "systemd" in str(self["init_target"]) and self["plymouth_kill"]:
        self.logger.warning("plymouth_kill is set with systemd as an init target, this may cause issues.")
    return f"""
    if ! plymouth --ping; then
        edebug "Plymouthd is not running, skipping stop"
        return 0
    fi
    plymouth --newroot="$(readvar SWITCH_ROOT_TARGET)"
    {"plymouth --quit" if self["plymouth_kill"] else ""}
    """
