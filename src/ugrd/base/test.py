__version__ = "2.0.0"

from pathlib import Path
from subprocess import PIPE, Popen
from selectors import DefaultSelector, EVENT_READ
from time import time
from uuid import uuid4

from zenlib.util import colorize as c_
from zenlib.util import unset


def _process_test_swap_partition(self, value):
    """Processes the 'test_swap_partition' configuration option to set up the swap UUID and related parameters"""
    if value and "ugrd.fs.resume" not in self["modules"]:
        self.logger.log(33, "test_swap_partiton enabled but 'ugrd.fs.resume' module not loaded, enabling it")
        self["modules"] = "ugrd.fs.resume"

    if not self["swap_uuid"]:
        self["swap_uuid"] = str(uuid4())
        self.logger.log(33, f"test_swap_partition enabled but no swap_uuid specified, generated random UUID: {c_(self['swap_uuid'], 'yellow')}")

    self.data["test_swap_partition"] = value


@unset("test_kernel")
def find_kernel_path(self):
    """Finds the kernel path for the current system"""
    self.logger.info("Trying to find the kernel path for: %s", c_(self["kernel_version"], "blue"))
    kernel_path = Path(self["_kmod_dir"]) / "vmlinuz"  # try this first
    if not (self["_kmod_dir"] / "vmlinuz").exists():
        for search_dir in ["/boot", "/efi"]:
            for prefix in ["vmlinuz", "kernel", "linux", "bzImage"]:
                kernel_path = Path(search_dir) / f"{prefix}-{self['kernel_version']}"
                if kernel_path.exists():
                    break
            if kernel_path.exists():
                break
        else:
            raise FileNotFoundError("Kernel not found: %s" % self["kernel_version"])

    self.logger.info("Found kernel at: %s", c_(kernel_path, "cyan"))
    self["test_kernel"] = kernel_path


def init_test_vars(self):
    """Initializes the test variables"""
    find_kernel_path(self)
    if not self["test_flag"]:
        self["test_flag"] = uuid4()


def _get_qemu_cmd_args(self, test_image):
    """Returns arguements to run QEMU for the current test configuration."""
    test_initrd = self._get_out_path(self["out_file"])
    self.logger.info("Testing initramfs image: %s", c_(test_initrd, "yellow", bold=True))
    test_rootfs = test_image._get_out_path(test_image["out_file"])
    self.logger.info(
        "Test rootfs image: %s",
        c_(
            test_rootfs,
            "yellow",
        ),
    )
    self.logger.info("Test kernel: %s", c_(self["test_kernel"], "yellow"))

    cmdline = self["test_cmdline"]
    if self["test_swap_partition"]:
        cmdline += f" resume=UUID={self['swap_uuid']}"

    qemu_args = {
        "-m": self["test_memory"],
        "-cpu": self["test_cpu"],
        "-kernel": self["test_kernel"],
        "-initrd": test_initrd,
        "-append": cmdline,
        "-drive": "file=%s,format=raw" % test_rootfs,
    }

    if self["test_no_rootfs"]:
        self.logger.warning(f"Removing QEMU drive option: {qemu_args.pop('-drive')}")

    qemu_bools = [f"-{item}" for item in self["qemu_bool_args"]]

    arglist = [f"qemu-system-{self['test_arch']}"] + qemu_bools
    for key, value in qemu_args.items():
        arglist.append(key)
        arglist.append(value)

    if self["test_swap_partition"]:
        arglist.append("-drive")
        arglist.append(f"file={self._get_out_path('swap.img')},format=raw")

    return arglist


def get_copy_config_types(self) -> dict:
    """Returns the 'custom_parameters' name, type pairs for config to be copied to the test image"""
    return {key: self["custom_parameters"][key] for key in self["test_copy_config"] if key in self["custom_parameters"]}


def make_test_image(self):
    """Creates a new initramfs generator to create the test image"""
    from ugrd.initramfs_generator import InitramfsGenerator

    kwargs = {
        "logger": self.logger,
        "validate": False,
        "NO_BASE": True,
        "config": None,
        "modules": "ugrd.fs.test_image",
        "out_file": self["test_rootfs_name"],
        "build_dir": self["test_rootfs_build_dir"],
        "custom_parameters": get_copy_config_types(self),
        "test_hibernate": self["test_swap_partition"],
        **{key: self.get(key) for key in self["test_copy_config"] if self.get(key) is not None},
    }

    target_fs = InitramfsGenerator(**kwargs)
    try:
        target_fs.build()
    except (FileNotFoundError, RuntimeError, PermissionError) as e:
        self.logger.error("Test image configuration:\n%s", target_fs)
        raise RuntimeError("Failed to build test rootfs: %s" % e)

    return target_fs

def make_swap_image(self):
    """Creates a swap image (detached partition) for testing swap support in the initramfs"""
    swap_path = self._get_out_path("swap.img")
    self.logger.log(33, f"Creating swap image at: {c_(swap_path, 'yellow', bold=True)}")

    if not self["test_memory"].endswith("M"):
        raise ValueError(
            "test_memory must be specified in megabytes (e.g. '512M') to create swap image: %s" % self["test_memory"]
        )

    swap_size = int(self["test_memory"][:-1])  # remove the 'M' suffix and convert to int
    try:
        bytes_size = swap_size * (2**20)  # convert megabytes to bytes
        with open(swap_path, "wb") as f:
            f.write(b"\0" * bytes_size)
    except (OSError, IOError) as e:
        self.logger.error("Failed to create swap image: %s", e)
        raise RuntimeError("Failed to create swap image: %s" % e)

    self._run(["mkswap", swap_path, "-U", self["swap_uuid"]])

def test_image(self, image=None, hibernate=False):
    """Runs the test image in QEMU
    If 'image' is not provided, it will be created using 'make_test_image'

    If hibernate is True, it is assumed that the test system is hibernated
    Do not re-create the test image, or swap image, simply boot the system again
    """
    image = image or make_test_image(self)
    if not hibernate and self["test_swap_partition"]:
        make_swap_image(self)

    qemu_cmd = _get_qemu_cmd_args(self, image)

    self.logger.debug("Test config:\n%s", image)
    self.logger.info("Test flag: %s", c_(self["test_flag"], "magenta"))
    self.logger.info("QEMU command: %s", c_(" ".join([str(arg) for arg in qemu_cmd]), bold=True))

    # Sentinel to check if the test has timed out
    start_time = time()
    test_timeout = self["test_timeout"]
    event_timeout = 1
    failed = False
    process = Popen(qemu_cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, close_fds=True)
    selector = DefaultSelector()
    selector.register(process.stdout, EVENT_READ)
    selector.register(process.stderr, EVENT_READ)

    run_log = []
    error_log = []

    try:
        while True:
            events = selector.select(timeout=event_timeout)

            if time() - start_time > test_timeout:
                self.logger.critical("Test timed out after %s seconds", test_timeout)
                failed = True
                break

            if not events:
                self.logger.warning("Timed out waiting for QEMU output")
                continue

            for key, _ in events:
                if key.fileobj == process.stderr:
                    line = process.stderr.readline()
                    if line:
                        self.logger.error(line.strip())
                        error_log.append(line)
                    else:
                        raise RuntimeError("QEMU stderr closed")
                elif key.fileobj == process.stdout:
                    # Read the line from stdout, remove the ANSI clear screen code
                    line = process.stdout.readline().replace("\x1bc\x1b[?7l", "")
                    if "\x1b" in line:
                        self.logger.debug("ANSI code detected in QEMU output: %s", repr(line))
                        line = line.replace("\x1b[2J", "")  # filter clear screen
                        line = line.replace("\x1b[0m", "")  # filter reset
                        self.logger.debug("Filtered ANSI code: %s", repr(line))
                    if line:
                        loglevel = 33 if self["qemu_stdout"] else 20
                        self.logger.log(loglevel, line.strip())
                    else:
                        raise RuntimeError("QEMU stdout closed")

            run_log.append(line)
            if self["test_flag"] in line:
                self.logger.info("Test flag found in output: %s", c_(line, "green"))
                break
            elif line.endswith("exitcode=0x00000000"):
                failed = True
                break
            elif "press space" in line.lower():
                self.logger.warning("Press space to continue message detected")
                process.stdin.write(" ")
                process.stdin.flush()
    except RuntimeError as e:
        if image["test_hibernate"]:
            if not hibernate:
                # Run a second pass for hibernation
                return test_image(self, image, hibernate=True)
            self.logger.critical("Test failed during hibernation phase: %s", e)
        self.logger.error("Error while reading QEMU output: %s", e)
        failed = True
    finally:
        selector.unregister(process.stdout)
        selector.unregister(process.stderr)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()

        process.kill()
        process.wait(timeout=1)

    if failed:
        self.logger.error(f"Tests failed: {' '.join([str(arg) for arg in qemu_cmd])}")
        self.logger.error(f"QEMU stdout: {''.join(run_log)}")
        self.logger.error(f"QEMU stderr: {''.join(error_log)}")
        raise RuntimeError("Test failed: %s" % qemu_cmd)
