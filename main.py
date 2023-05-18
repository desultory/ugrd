#!/usr/bin/env python

from initramfs_generator import InitramfsGenerator

import logging


if __name__ == '__main__':
    logging.getLogger().setLevel(20)
    generator = InitramfsGenerator()
