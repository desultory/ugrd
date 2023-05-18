#!/usr/bin/env python

from initramfs_generator import InitramfsGenerator

import logging


if __name__ == '__main__':
    logging.getLogger().setLevel(5)
    generator = InitramfsGenerator(clean=False)
