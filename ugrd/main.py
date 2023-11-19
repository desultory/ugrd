#!/usr/bin/env python

from ugrd.initramfs_generator import InitramfsGenerator
from ugrd.zen_custom import ColorLognameFormatter

from argparse import ArgumentParser
import logging


def main():
    argparser = ArgumentParser(prog='ugrd',
                               description='MicrogRAM disk initramfs generator')

    argparser.add_argument('-d', '--debug', action='store_true', help='Debug mode')
    argparser.add_argument('-dd', '--verbose-debug', action='store_true', help='Verbose debug mode')

    # Add arguments for dracut compatibility
    argparser.add_argument('-c', '--config', action='store', help='Config file location')
    argparser.add_argument('--kver', action='store', help='Kernel version')
    argparser.add_argument('--force', action='store_true', help='Enable build cleaning', default=True)

    # Add and ignore arguments for dracut compatibility
    argparser.add_argument('--kernel-image', action='store', help='Kernel image')

    # Add the argument for the output file
    argparser.add_argument('output_file', action='store', help='Output file location', nargs='?')

    args = argparser.parse_args()

    # Set the initial logger debug level based on the args, set the format string based on the debug level
    logger = logging.getLogger()
    if args.verbose_debug:
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

    for config, arg in {'clean': 'force', 'kernel_version': 'kver', 'config': 'config', 'out_file': 'output_file'}.items():
        if arg := getattr(args, arg):
            kwargs[config] = arg

    generator = InitramfsGenerator(**kwargs)
    try:
        generator.build_structure()
        generator.generate_init()
        generator.pack_build()
    except Exception as e:
        logger.info("Dumping config dict:\n")
        print(generator.config_dict)
        logger.error(e, exc_info=True)


if __name__ == '__main__':
    main()

