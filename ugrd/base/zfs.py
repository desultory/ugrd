

def mount_zfs_root(self):
    """
    Mounts the ZFS root pool
    """
    return [f"zpool import -R /mnt/gentoo {self.config_dict['root_mount']['source']['label']}", 'zfs mount -a']
