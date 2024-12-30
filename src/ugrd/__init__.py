from .initramfs_generator import InitramfsGenerator

class ValidationError(Exception):
    pass

class AutodetectError(Exception):
    pass

__all__ = ["InitramfsGenerator"]
