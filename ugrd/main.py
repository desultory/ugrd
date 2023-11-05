#!/usr/bin/env python

from ugrd.initramfs_generator import InitramfsGenerator
from ugrd.zen_custom import pretty_print

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

    logger = logging.getLogger()
    if args.verbose_debug:
        logger.setLevel(5)
    elif args.debug:
        logger.setLevel(10)
    else:
        logger.setLevel(20)

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
        logger.error("\n\nError: %s\n\n" % e, exc_info=True)
        logger.info("Dumping config dict:\n")
        pretty_print(generator.config_dict)


if __name__ == '__main__':
    main()

