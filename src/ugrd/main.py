#!/usr/bin/env python

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.util import get_kwargs_from_args, get_args_n_logger


def main():
    arguments = [{'flags': ['--build-logging'], 'action': 'store_true', 'help': 'enable additional build logging'},
                 {'flags': ['--no-build-logging'], 'action': 'store_false', 'help': 'disable additional build logging', 'dest': 'build_logging'},
                 {'flags': ['-c', '--config'], 'action': 'store', 'help': 'set the config file location'},
                 {'flags': ['--kernel-version', '--kver'], 'action': 'store', 'help': 'set the kernel version'},
                 {'flags': ['--clean'], 'action': 'store_true', 'help': 'clean the build directory at runtime'},
                 {'flags': ['--no-clean'], 'action': 'store_false', 'help': 'disable build directory cleaning', 'dest': 'clean'},
                 {'flags': ['--validate'], 'action': 'store_true', 'help': 'enable configuration validation'},
                 {'flags': ['--no-validate'], 'action': 'store_false', 'help': 'disable config validation', 'dest': 'validate'},
                 {'flags': ['--hostonly'], 'action': 'store_true', 'help': 'enable hostonly mode, required for automatic kmod detection'},
                 {'flags': ['--no-hostonly'], 'action': 'store_false', 'help': 'disable hostonly mode', 'dest': 'hostonly'},
                 {'flags': ['--lspci'], 'action': 'store_true', 'help': 'use lspci to auto-detect kmods', 'dest': 'kmod_autodetect_lspci'},
                 {'flags': ['--no-lspci'], 'action': 'store_false', 'help': 'do not use lspci to auto-detect kmods', 'dest': 'kmod_autodetect_lspci'},
                 {'flags': ['--lsmod'], 'action': 'store_true', 'help': 'use lsmod to auto-detect kmods', 'dest': 'kmod_autodetect_lsmod'},
                 {'flags': ['--no-lsmod'], 'action': 'store_false', 'help': 'do not use lsmod to auto-detect kmods', 'dest': 'kmod_autodetect_lsmod'},
                 {'flags': ['--firmware'], 'action': 'store_true', 'help': 'include firmware files found with modinfo', 'dest': 'kmod_pull_firmware'},
                 {'flags': ['--no-firmware'], 'action': 'store_false', 'help': 'exclude firmware files', 'dest': 'kmod_pull_firmware'},
                 {'flags': ['--autodetect-root'], 'action': 'store_true', 'help': 'autodetect the root partition'},
                 {'flags': ['--no-autodetect-root'], 'action': 'store_false', 'help': 'do not autodetect the root partition', 'dest': 'autodetect_root'},
                 {'flags': ['--autodetect-root-luks'], 'action': 'store_true', 'help': 'autodetect LUKS volumes under the root partition'},
                 {'flags': ['--no-autodetect-root-luks'], 'action': 'store_false', 'help': 'do not autodetect root LUKS volumes', 'dest': 'autodetect_root_luks'},
                 {'flags': ['--print-config'], 'action': 'store_true', 'help': 'print the final config dict'},
                 {'flags': ['out_file'], 'action': 'store', 'help': 'set the output image location', 'nargs': '?'}]

    args, logger = get_args_n_logger(package=__package__, description='MicrogRAM disk initramfs generator', arguments=arguments, drop_default=True)
    kwargs = get_kwargs_from_args(args, logger=logger)
    kwargs.pop('print_config', None)  # This is not a valid kwarg for InitramfsGenerator

    logger.debug(f"Using the following kwargs: {kwargs}")
    generator = InitramfsGenerator(**kwargs)

    try:
        generator.build()
    except Exception as e:
        logger.info("Dumping config dict:\n")
        print(generator.config_dict)
        logger.error(e, exc_info=True)
        exit(1)

    if 'print_config' in args and args.print_config:
        print(generator.config_dict)


if __name__ == '__main__':
    main()

