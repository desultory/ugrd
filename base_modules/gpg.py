def symlink_pinentry(self):
    """
    Symlink pinentry
    """
    pinentry = self.config_dict.get('pinentry', 'pinentry-tty')
    return [f"ln -s /usr/bin/{pinentry} /usr/bin/pinentry"]
