__author__ = 'desultory'
__version__ = '2.1.0'


from pycpio import PyCPIO


def make_cpio(self) -> None:
    cpio = PyCPIO(logger=self.logger, _log_bump=5)
    cpio.append_recursive(self.build_dir, relative=True)

    if self.config_dict['mknod_cpio']:
        for node in self.config_dict['nodes'].values():
            self.logger.debug("Adding CPIO node: %s" % node)
            cpio.add_chardev(name=node['path'], mode=node['mode'], major=node['major'], minor=node['minor'])

    out_cpio = self.out_dir / self.config_dict['out_file']
    if out_cpio.exists():
        self._rotate_old(out_cpio)

    cpio.write_cpio_file(out_cpio)
