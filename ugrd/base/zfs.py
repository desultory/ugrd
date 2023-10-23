__author__ = 'desultory'
__version__ = '0.0.1'


def mount_zfs_root(self):
    """
    Mounts the ZFS root pool
    """
    zpool_cmd = f"zpool import -R /mnt/root {self.config_dict['root_mount']['source']['label']} || (echo 'Failed to import ZFS root pool' && bash)"
    zmount_cmd = "zfs mount -a || (echo 'Failed to mount ZFS root.' && bash)"

    return [zpool_cmd, zmount_cmd]
