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
        if [ ! -e "${dm}/uevent" ]; then
            continue
        fi
        . "${dm}/uevent"
        einfo "Faking udev for: ${DEVNAME}"
        udev_db_file="/run/udev/data/b${MAJOR}:${MINOR}"
        printf 'E:DM_UDEV_PRIMARY_SOURCE_FLAG=1\n' > "${udev_db_file}"
    done
    """
