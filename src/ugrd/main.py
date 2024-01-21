#!/usr/bin/env python

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.util import get_kwargs_from_args, get_args_n_logger


def main():
    arguments = [{'flags': ['--build-logging'], 'action': 'store_true', 'help': 'Enable additional build logging.'},
                 {'flags': ['--no-build-logging'], 'action': 'store_false', 'help': 'Disable additional build logging.', 'dest': 'build_logging'},
                 {'flags': ['-c', '--config'], 'action': 'store', 'help': 'Config file location.'},
                 {'flags': ['--kernel-version', '--kver'], 'action': 'store', 'help': 'Set the kernel version.'},
                 {'flags': ['--clean'], 'action': 'store_true', 'help': 'Enable build directory cleaning.', 'default': True},
                 {'flags': ['--no-clean'], 'action': 'store_false', 'help': 'Disable build directory cleaning.', 'dest': 'clean'},
                 {'flags': ['--validate'], 'action': 'store_true', 'help': 'Enable config validation.', 'default': True},
                 {'flags': ['--no-validate'], 'action': 'store_false', 'help': 'Disable config validation.', 'dest': 'validate'},
                 {'flags': ['--hostonly'], 'action': 'store_true', 'help': 'Enable hostonly mode, required for automatic kmod detection.', 'default': True},
                 {'flags': ['--no-hostonly'], 'action': 'store_false', 'help': 'Disable hostonly mode.', 'dest': 'hostonly'},
                 {'flags': ['--lspci'], 'action': 'store_true', 'help': 'Use lspci to auto-detect kmods', 'dest': 'kmod_autodetect_lspci'},
                 {'flags': ['--no-lspci'], 'action': 'store_false', 'help': 'Do not use lspci to auto-detect kmods', 'dest': 'kmod_autodetect_lspci'},
                 {'flags': ['--lsmod'], 'action': 'store_true', 'help': 'Use lsmod to auto-detect kmods', 'dest': 'kmod_autodetect_lsmod'},
                 {'flags': ['--no-lsmod'], 'action': 'store_false', 'help': 'Do not use lsmod to auto-detect kmods', 'dest': 'kmod_autodetect_lsmod'},
                 {'flags': ['--firmware'], 'action': 'store_true', 'help': 'Include firmware files found with modinfo.', 'dest': 'kmod_pull_firmware', 'default': True},
                 {'flags': ['--no-firmware'], 'action': 'store_false', 'help': 'Exclude firmware files.', 'dest': 'kmod_pull_firmware'},
                 {'flags': ['--autodetect-root'], 'action': 'store_true', 'help': 'Autodetect the root partition.', 'default': True},
                 {'flags': ['--no-autodetect-root'], 'action': 'store_false', 'help': 'Do not autodetect the root partition.', 'dest': 'autodetect_root'},
                 {'flags': ['--print-config'], 'action': 'store_true', 'help': 'Print the final config dict.'},
                 {'flags': ['out_file'], 'action': 'store', 'help': 'Output file location', 'nargs': '?'}]

    args, logger = get_args_n_logger(package=__package__, description='MicrogRAM disk initramfs generator', arguments=arguments)
    kwargs = get_kwargs_from_args(args, logger=logger)
    kwargs.pop('print_config')  # This is not a valid kwarg for InitramfsGenerator

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

