def custom_init(self):
    """
    init override
    """
    from os import chmod
    with open(f"{self.out_dir}/init_main.sh", 'w', encoding='utf-8') as main_init:
        main_init.write("#!/bin/bash\n")
        [main_init.write(f"{line}\n") for line in self.generate_init_main()]
    chmod(f"{self.out_dir}/init_main.sh", 0o755)
    return serial_init(self)


def serial_init(self):
    """
    start agetty
    """
    try:
        out = list()
        for name, config in self.config_dict['serial'].items():
            if config.get('local'):
                out.append(f"agetty --autologin root --login-program /init_main.sh -L {config['baud']} {name} {config['type']}")
            else:
                out.append(f"agetty --autologin root --login-program /init_main.sh {config['baud']} {name} {config['type']}")
        return out
    except (KeyError, AttributeError):
        self.logger.error("UNABLE TO COFIGURE SERIAL")
        self.logger.error("""
                          A serial dict configured with:
                          serial:
                            interface_name:
                              baud: baud rate
                              type: interface type
                          optional config:
                            local: bool - controls the -L flag for agetty
                          ex:
                          serial:
                            ttyS1:
                              baud: 115200
                              type: vt100
                          """)
