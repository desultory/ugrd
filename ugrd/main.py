#!/usr/bin/env python

from ugrd.initramfs_generator import InitramfsGenerator
from ugrd.zen_custom import pretty_print

from argparse import ArgumentParser
import logging


def main():
    argparser = ArgumentParser(prog='ugrd',
                               description='MicrogRAM disk initramfs generator')

    argparser.add_argument('config_file',
                           action='store',
                           nargs='?',
                           help='Config file location')

    argparser.add_argument('-d', '--debug', action='store_true', help='Debug mode')
    argparser.add_argument('-dd', '--verbose-debug', action='store_true', help='Verbose debug mode')

    args = argparser.parse_args()

    logger = logging.getLogger()
    if args.verbose_debug:
        logger.setLevel(5)
    elif args.debug:
        logger.setLevel(10)
    else:
        logger.setLevel(20)

    kwargs = {'logger': logger}
    if config := args.config_file:
        kwargs['config'] = config

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

