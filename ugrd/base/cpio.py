__author__ = "desultory"
__version__ = "0.0.2"

from subprocess import run


def pack_cpio(self):
    """
    Packs the CPIO file using gen_init_cpio
    """
    if not self.config_dict['gen_init_cpio_path'].exists():
        raise FileNotFoundError("gen_init_cpio not found at: %s" % self.config_dict['gen_init_cpio_path'])
    gen_init_cpio = str(self.config_dict['gen_init_cpio_path'])

    self.logger.debug("Using gen_init_cpio at: %s" % self.config_dict['gen_init_cpio_path'])

    packing_list = str(self.out_dir / self.config_dict['cpio_list_name'])
    self.logger.info("Creating CPIO file from packing list: %s" % packing_list)

    out_cpio = self.out_dir / self.config_dict['cpio_filename']

    with open(out_cpio, 'wb') as cpio_file:
        cmd = run([gen_init_cpio, packing_list], stdout=cpio_file)
        if cmd.returncode != 0:
            raise RuntimeError("gen_init_cpio failed with error: %s" % cmd.stderr.decode())

    self.logger.info("CPIO file created at: %s" % out_cpio)
    self._chown(out_cpio)


def generate_cpio_mknods(self):
    """
    Generate all of the node entries for the CPIO from self.config_dict['nodes']
    """
    node_list = []

    for node in self.config_dict["nodes"].values():
        self.logger.debug("Adding CPIO node: %s" % node)
        node_list.append(f"nod {node['path']} {str(oct(node['mode'] & 0o777))[2:]} 0 0 c {node['major']} {node['minor']}")

    self.logger.debug("CPIO node list: %s" % node_list)
    return node_list


def make_cpio_list(self):
    """
    Generates a CPIO list file for gen_init_cpio.

    All folders and files in self.build_dir are included.
    The file uid and gid will be set to 0 within the cpio.
    Device node information will be included if nodes are in the path,
    if cpio_nodes is set to true, nodes will be created in the cpio only.

    The cpio packing list is written to self.out_dir/cpio.list
    """
    from os import walk, minor, major
    from pathlib import Path

    directory_list = []
    file_list = []
    symlink_list = []
    node_list = []

    for root_dir, dirs, files in walk(self.build_dir):
        current_dir = Path(root_dir)
        relative_dir = current_dir.relative_to(self.build_dir)

        if relative_dir == Path("."):
            self.logger.log(5, "Skipping root directory")
        else:
            directory_perms = str(oct(current_dir.stat().st_mode & 0o777))[2:]
            directory_list.append(f"dir /{str(relative_dir)} {str(directory_perms)} 0 0")

        for file in files:
            file_dest = relative_dir / file
            file_source = current_dir / file
            if file_source.is_symlink():
                symlink_list.append(f"slink /{file_dest} /{file_source.resolve().relative_to(self.build_dir)} 777 0 0")
            elif file_source.is_char_device():
                node_major = major(file_source.stat().st_rdev)
                node_minor = minor(file_source.stat().st_rdev)
                node_perms = str(oct(file_source.stat().st_mode & 0o777))[2:]
                node_list.append(f"nod /{file_dest} {node_perms} 0 0 c {node_major} {node_minor}")
            elif file_source.is_block_device():
                raise NotImplementedError("Block devices are not supported")
            else:
                file_perms = str(oct(file_source.stat().st_mode & 0o777))[2:]
                file_entry = f"file /{file_dest} {file_source} {file_perms} 0 0"
                file_list.append(file_entry)

    if self.config_dict['mknod_cpio'] or True:
        for node in generate_cpio_mknods(self):
            if node not in node_list:
                node_list.append(node)
            else:
                self.logger.warning("Duplicate node entry: %s" % node)

    self.logger.debug("CPIO directory list: %s" % directory_list)
    self.logger.debug("CPIO file list: %s" % file_list)
    self.logger.debug("CPIO symlink list: %s" % symlink_list)
    self.logger.debug("CPIO node list: %s" % node_list)

    packing_list = directory_list + file_list + symlink_list + node_list

    self._write(self.out_dir / self.config_dict['cpio_list_name'], packing_list, in_build_dir=False)

