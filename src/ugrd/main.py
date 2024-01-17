#!/usr/bin/env python

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.util import init_logger, init_argparser, process_args


def main():
    logger = init_logger(__package__)
    argparser = init_argparser(prog=__package__, description='MicrogRAM disk initramfs generator')

    argparser.add_argument('--build-logging', action='store_true', help='Enable additional build logging.')
    argparser.add_argument('--no-build-logging', action='store_true', help='Disable additional build logging.')

    # Add arguments for dracut compatibility
    argparser.add_argument('-c', '--config', action='store', help='Config file location.')
    argparser.add_argument('--kver', action='store', help='Set the kernel version.')

    argparser.add_argument('--clean', action='store_true', help='Enable build directory cleaning.')
    argparser.add_argument('--no-clean', action='store_true', help='Disable build directory cleaning.')

    argparser.add_argument('--validate', action='store_true', help='Enable config validation.')
    argparser.add_argument('--no-validate', action='store_true', help='Disable config validation.')

    argparser.add_argument('--hostonly', action='store_true', help='Enable hostonly mode, required for automatic kmod detection.')
    argparser.add_argument('--no-hostonly', action='store_true', help='Disable hostonly mode.')

    # Add arguments for auto-kmod detection
    argparser.add_argument('--lspci', action='store_true', help='Use lspci to auto-detect kmods')
    argparser.add_argument('--lsmod', action='store_true', help='Use lsmod to auto-detect kmods')

    # Add argument for firmware inclusion
    argparser.add_argument('--firmware', action='store_true', help='Include firmware files found with modinfo.')
    argparser.add_argument('--no-firmware', action='store_true', help='Exclude firmware files.')

    # Add argument for autodecting the root partition
    argparser.add_argument('--autodetect-root', action='store_true', help='Autodetect the root partition.')
    argparser.add_argument('--no-autodetect-root', action='store_true', help='Do not autodetect the root partition.')

    # Add the argument for the output file
    argparser.add_argument('output_file', action='store', help='Output file location', nargs='?')

    # Print the final config_dict
    argparser.add_argument('--print-config', action='store_true', help='Print the final config dict.')

    args = process_args(argparser, logger=logger)

    # Pass the logger to the generator
    kwargs = {'logger': logger}

    # Set config toggles
    for toggle in ['validate', 'hostonly', 'firmware', 'autodetect_root', 'clean', 'build_logging']:
        if arg := getattr(args, f"no_{toggle}"):
            kwargs[toggle] = False

    for config, arg in {'clean': 'clean',
                        'kernel_version': 'kver',
                        'kmod_autodetect_lspci': 'lspci',
                        'kmod_autodetect_lsmod': 'lsmod',
                        'autodetect_root': 'autodetect_root',
                        'validate': 'validate',
                        'hostonly': 'hostonly',
                        'build_logging': 'build_logging',
                        'config': 'config',
                        'out_file': 'output_file'}.items():
        if arg := getattr(args, arg):
            kwargs[config] = arg

    logger.debug(f"Using the following kwargs: {kwargs}")

    generator = InitramfsGenerator(**kwargs)
    try:
        generator.build()
    except Exception as e:
        logger.info("Dumping config dict:\n")
        print(generator.config_dict)
        logger.error(e, exc_info=True)
        exit(1)

    if args.print_config:
        print(generator.config_dict)


if __name__ == '__main__':
    main()

