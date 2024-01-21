#!/usr/bin/env python

from ugrd.initramfs_generator import InitramfsGenerator
from zenlib.util import get_kwargs_from_args, get_args_n_logger


def main():
    arguments = [{'flags': ['--build-logging'], 'action': 'store_true', 'help': 'Enable additional build logging.'},
                 {'flags': ['--no-build-logging'], 'action': 'store_true', 'help': 'Disable additional build logging.'},
                 {'flags': ['-c', '--config'], 'action': 'store', 'help': 'Config file location.'},
                 {'flags': ['--kver'], 'action': 'store', 'help': 'Set the kernel version.'},
                 {'flags': ['--clean'], 'action': 'store_true', 'help': 'Enable build directory cleaning.'},
                 {'flags': ['--no-clean'], 'action': 'store_true', 'help': 'Disable build directory cleaning.'},
                 {'flags': ['--validate'], 'action': 'store_true', 'help': 'Enable config validation.'},
                 {'flags': ['--no-validate'], 'action': 'store_true', 'help': 'Disable config validation.'},
                 {'flags': ['--hostonly'], 'action': 'store_true', 'help': 'Enable hostonly mode, required for automatic kmod detection.'},
                 {'flags': ['--no-hostonly'], 'action': 'store_true', 'help': 'Disable hostonly mode.'},
                 {'flags': ['--lspci'], 'action': 'store_true', 'help': 'Use lspci to auto-detect kmods'},
                 {'flags': ['--lsmod'], 'action': 'store_true', 'help': 'Use lsmod to auto-detect kmods'},
                 {'flags': ['--firmware'], 'action': 'store_true', 'help': 'Include firmware files found with modinfo.'},
                 {'flags': ['--no-firmware'], 'action': 'store_true', 'help': 'Exclude firmware files.'},
                 {'flags': ['--autodetect-root'], 'action': 'store_true', 'help': 'Autodetect the root partition.'},
                 {'flags': ['--no-autodetect-root'], 'action': 'store_true', 'help': 'Do not autodetect the root partition.'},
                 {'flags': ['--print-config'], 'action': 'store_true', 'help': 'Print the final config dict.'},
                 {'flags': ['output_file'], 'action': 'store', 'help': 'Output file location', 'nargs': '?'}]

    args, logger = get_args_n_logger(package=__package__, description='MicrogRAM disk initramfs generator', arguments=arguments)
    kwargs = get_kwargs_from_args(args, logger=logger)

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

