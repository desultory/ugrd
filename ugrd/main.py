#!/usr/bin/env python

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.logging import ColorLognameFormatter

from argparse import ArgumentParser
import logging


def main():
    argparser = ArgumentParser(prog='ugrd',
                               description='MicrogRAM disk initramfs generator')

    argparser.add_argument('-d', '--debug', action='store_true', help='Debug mode')
    argparser.add_argument('-dd', '--verbose', action='store_true', help='Verbose debug mode')

    # Add arguments for dracut compatibility
    argparser.add_argument('-c', '--config', action='store', help='Config file location')
    argparser.add_argument('--kver', action='store', help='Kernel version')
    argparser.add_argument('--force', action='store_true', help='Enable build cleaning')
    argparser.add_argument('--hostonly', action='store_true', help='Enable hostonly mode')
    argparser.add_argument('--no-hostonly', action='store_true', help='Disable hostonly mode')

    # Add and ignore arguments for dracut compatibility
    argparser.add_argument('--kernel-image', action='store', help='Kernel image (ignored)')

    # Add arguments for auto-kmod detection
    argparser.add_argument('--lspci', action='store_true', help='Use lspci to auto-detect kmods')
    argparser.add_argument('--lsmod', action='store_true', help='Use lsmod to auto-detect kmods')

    # Add argument for firmware inclusion
    argparser.add_argument('--firmware', action='store_true', help='Include firmware')
    argparser.add_argument('--no-firmware', action='store_true', help='Exclude firmware')

    # Add the argument for the output file
    argparser.add_argument('output_file', action='store', help='Output file location', nargs='?')

    args = argparser.parse_args()

    # Set the initial logger debug level based on the args, set the format string based on the debug level
    logger = logging.getLogger()
    if args.verbose:
        logger.setLevel(5)
        formatter = ColorLognameFormatter('%(time)s | %(levelname)s | %(name)-42s | %(message)s')
    elif args.debug:
        logger.setLevel(10)
        formatter = ColorLognameFormatter('%(levelname)s | %(name)-42s | %(message)s')
    else:
        logger.setLevel(20)
        formatter = ColorLognameFormatter()

    # Add the handler to the logger
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Pass the logger to the generator
    kwargs = {'logger': logger}

    if args.no_hostonly:
        kwargs['hostonly'] = False
    elif args.hostonly:
        kwargs['hostonly'] = True

    if args.no_firmware:
        kwargs['kmod_pull_firmware'] = False
    elif args.firmware:
        kwargs['kmod_pull_firmware'] = True

    for config, arg in {'clean': 'force',
                        'kernel_version': 'kver',
                        'kmod_autodetect_lspci': 'lspci',
                        'kmod_autodetect_lsmod': 'lsmod',
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


if __name__ == '__main__':
    main()

