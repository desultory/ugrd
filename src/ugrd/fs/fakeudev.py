"""
UDEV is amazing and well desinged software.

In order to make systemd not time out on boot, we need to fake it.
To do this, we simply need to read /sys/block/dm-*/uevent,
We can then write 'E:DM_UDEV_PRIMARY_SOURCE_FLAG=1\n' to each:
    /run/udev/data/b<MAJOR>:<MINOR>.
This will make systemd think that udev is working and not time out.
"""


def fake_dm_udev(self) -> str:
    """returns a shell function to fake udev for dm devices.
    Previously, ${dm}/uevent was sourced, but this has the potential to crash the shell

    Checks for the existence of /sys/block/dm-* entries,
    for each entry, it checks if the device has a 'dev' and name file, it not, skips it.
    Fully initailzed deviecs should have a 'dm/name' file.

    Reads the 'dev' file to get the device's major and minor numbers,
    uses these to create a udev database file in /run/udev/data/b<MAJOR>:<MINOR>.
    writes 'E:DM_UDEV_PRIMARY_SOURCE_FLAG=1\n' to this file, which signals to systemd that udev is functioning for this device.
    """
    return r"""
    for dm in /sys/block/dm-*; do
        if [ ! -e "${dm}/dev" ]; then
            ewarn "Skipping fakeudev for device without 'dev' file: ${dm}"
            continue
        fi
        if [ ! -e "${dm}/dm/name" ]; then
            ewarn "Skipping fakeudev for device without 'dm/name' file: ${dm}"
            continue
        fi
        dev_name=$(cat ${dm}/dm/name)
        majmin=$(cat "${dm}/dev")
        einfo "[${majmin}] Faking udev for: ${dev_name}"
        udev_db_file="/run/udev/data/b${majmin}"
        printf 'E:DM_UDEV_PRIMARY_SOURCE_FLAG=1\n' > "${udev_db_file}"
    done
    """
