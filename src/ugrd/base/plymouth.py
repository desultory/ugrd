

def populate_initrd(self):
    """
    Runs /usr/libexec/plymouth/plymouth-populate-initrd
    """
    self._run(['/usr/libexec/plymouth/plymouth-populate-initrd', '-t', self.build_dir])


def start_plymouth(self):
    """
    Runs plymouthd
    """
    return ['plymouthd --attach-to-session --pid-file /run/plymouth/pid --mode=boot', 'plymouth show-splash']
