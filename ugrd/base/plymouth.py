

def populate_initrd(self):
    """
    Runs /usr/libexec/plymouth/plymouth-populate-initrd
    """
    self._run(['/usr/libexec/plymouth/plymouth-populate-initrd', '-t', self.out_dir])


def start_plymouth(self):
    """
    Runs plymouthd
    """
    return ['/usr/sbin/plymouthd --attach-to-session --pid-file /run/plymouth/pid --mode=boot']
