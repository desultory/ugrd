"""
UDEV is amazing and well desinged software.

In order to make systemd not time out on boot, we need to fake it.
To do this, we simply need to read /sys/block/dm-*/uevent,
We can then write 'E:DM_UDEV_PRIMARY_SOURCE_FLAG=1\n' to each:
    /run/udev/data/b<MAJOR>:<MINOR>.
This will make systemd think that udev is working and not time out.
"""


def fake_dm_udev(self) -> str:
    """returns a shell function to fake udev for dm devices."""
    return r"""
    for dm in /sys/block/dm-*; do
        if [ ! -e "${dm}/dev" ]; then
            continue
        fi
        if [ ! -e "${dm}/dm/name" ]; then
            continue
        fi
        dev_name=$(cat ${dm}/dm/name)
        majmin=$(cat "${dm}/dev")
        einfo "Faking udev for: ${dev_name}"
        udev_db_file="/run/udev/data/b${majmin}"
        printf 'E:DM_UDEV_PRIMARY_SOURCE_FLAG=1\n' > "${udev_db_file}"
    done
    """
