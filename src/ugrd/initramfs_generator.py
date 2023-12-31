
from tomllib import load
from typing import Union
from pathlib import Path
from subprocess import run, CompletedProcess

from zen_logging import loggify
from zen_util import pretty_print

from ugrd.initramfs_dict import InitramfsConfigDict

from importlib.metadata import version

__version__ = version(__package__)
__author__ = "desultory"


@loggify
class InitramfsGenerator:
    def __init__(self, config='/etc/ugrd/config.toml', *args, **kwargs):
        self.config_filename = config
        self.config_dict = InitramfsConfigDict(logger=self.logger)

        # Used for functions that are added to the bash source file
        self.included_functions = {}

        # Used for functions that are run as part of the build process, build_final is run after init generation
        self.build_tasks = ['build_pre', 'build_tasks']

        # init_pre and init_final are run as part of generate_initramfs_main
        self.init_types = ['init_debug', 'init_early', 'init_main', 'init_late', 'init_premount', 'init_mount', 'init_cleanup']

        self.load_config()
        self.config_dict.import_args(kwargs)
        self.config_dict.validate()

    def load_config(self) -> None:
        """
        Loads the config from the specified toml file.
        Populates self.config_dict with the config.
        Ensures that the required parameters are present.
        """
        with open(self.config_filename, 'rb') as config_file:
            self.logger.info("Loading config file: %s" % config_file.name)
            raw_config = load(config_file)

        # Process into the config dict, it should handle parsing
        for config, value in raw_config.items():
            self.logger.debug("Processing config key: %s" % config)
            self[config] = value

        self.logger.debug("Loaded config:\n%s" % self.config_dict)

    def __setitem__(self, key, value):
        self.config_dict[key] = value

    def __getitem__(self, item):
        return self.config_dict[item]

    def __contains__(self, item):
        return item in self.config_dict

    def get(self, item, default=None):
        return self.config_dict.get(item, default)

    def __getattr__(self, item):
        """ Allows access to the config dict via the InitramfsGenerator object. """
        if item not in self.__dict__:
            if item not in self.config_dict['required_parameters']:
                self.logger.warning("Accessing non-required parameter through getattr -> config_dict: %s" % item)
            return self[item]
        return super().__getattr__(item)

    def build(self) -> None:
        """ Builds the initramfs. """
        self.logger.info("Building initramfs")
        self.build_structure()
        self.generate_init()
        self._run_hook('build_final')
        self.pack_build()

    def build_structure(self) -> None:
        """ builds the initramfs structure. """
        for hook in self.build_tasks:
            self._run_hook(hook)

    def _run_func(self, function, force_include=False) -> list[str]:
        """ Runs a function, If force_include is set, forces the function to be included in the bash source file. """
        self.logger.log(self['_build_log_level'], "Running function: %s" % function.__name__)

        if function_output := function(self):
            if isinstance(function_output, list) and len(function_output) == 1:
                self.logger.debug("[%s] Function returned list with one element: %s" % (function.__name__, function_output[0]))
                function_output = function_output[0]

            if function.__name__ in self.included_functions:
                raise ValueError("Function '%s' has already been included in the bash source file" % function.__name__)

            if function.__name__ in self['binaries']:
                raise ValueError("Function name collides with defined binary: %s" % (function.__name__))
                return function_output

            if isinstance(function_output, str) and not force_include:
                self.logger.debug("[%s] Function returned string: %s" % (function.__name__, function_output))
                return function_output

            self.logger.debug("[%s] Function returned output: %s" % (function.__name__, pretty_print(function_output)))
            self.included_functions[function.__name__] = function_output
            self.logger.debug("Created function alias: %s" % function.__name__)
            return function.__name__
        else:
            self.logger.debug("[%s] Function returned no output" % function.__name__)

    def _run_hook(self, hook: str, *args, **kwargs) -> list[str]:
        """ Runs a hook for imported functions. """
        out = []
        for function in self['imports'].get(hook, []):
            if function_output := self._run_func(function, *args, **kwargs):
                out.append(function_output)
        return out

    def _run_init_hook(self, level: str) -> list[str]:
        """ Runs the specified init hook, returning the output. """
        if runlevel := self._run_hook(level):
            out = ['\n\n# Begin %s' % level]
            out += runlevel
            return out
        else:
            self.logger.debug("No output for init level: %s" % level)

    def generate_init_funcs(self) -> None:
        """ Generates the init functions file based on self.included_functions. """
        out = [f"# Generated by UGRD v{__version__}"]

        for func_name, func_content in self.included_functions.items():
            out.append("\n\n" + func_name + "() {")
            if isinstance(func_content, str):
                out.append(f"    {func_content}")
            elif isinstance(func_content, list):
                for line in func_content:
                    out.append(f"    {line}")
            else:
                raise TypeError("Function content is not a string or list: %s" % func_content)
            out.append("}")

        return out

    def generate_init_main(self) -> list[str]:
        """
        Generates the main init file.
        Just runs each hook  in self.init_types and returns the output
        """
        out = []
        for init_type in self.init_types:
            if runlevel := self._run_init_hook(init_type):
                out.extend(runlevel)
        return out

    def generate_init(self) -> None:
        """ Generates the init file. """
        self.logger.info("Running init generator functions")

        init = [self['shebang']]
        init += [f'echo "Starting UGRD v{__version__}"']

        # Run all included functions, so they get included
        self._run_hook('functions', force_include=True)

        init.extend(self._run_init_hook('init_pre'))

        if self['imports'].get('custom_init') and self.get('_custom_init_file'):
            init += ["\n\n# !!custom_init"]
            init_line, custom_init = self['imports']['custom_init'](self)
            if isinstance(init_line, str):
                init.append(init_line)
            else:
                init.extend(init_line)
        else:
            init.extend(self.generate_init_main())

        init.extend(self._run_init_hook('init_final'))
        init += ["\n\n# END INIT"]

        if self.included_functions:
            init_funcs = self.generate_init_funcs()
            self._write('init_funcs.sh', init_funcs, 0o755)
            self.logger.info("Included functions: %s" % list(self.included_functions.keys()))
            init.insert(3, "source init_funcs.sh")
            if self['imports'].get('custom_init'):
                custom_init.insert(2, f"echo 'Starting custom init, UGRD v{__version__}'")
                custom_init.insert(2, "source /init_funcs.sh")

        if self.get('_custom_init_file'):
            self._write(self['_custom_init_file'], custom_init, 0o755)

        self._write('init', init, 0o755)
        self.logger.debug("Final config:\n%s" % pretty_print(self.config_dict))

    def pack_build(self) -> None:
        """ Packs the initramfs based on self['imports']['pack']."""
        if self['imports'].get('pack'):
            self._run_hook('pack')
        else:
            self.logger.warning("No pack functions specified, the final build is present in: %s" % self.build_dir)

    def _get_build_path(self, path: Union[Path, str]) -> Path:
        """ Returns the build path. """
        if not isinstance(path, Path):
            path = Path(path)

        if path.is_absolute():
            return self.build_dir / path.relative_to('/')
        else:
            return self.build_dir / path

    def _mkdir(self, path: Path) -> None:
        """ Creates a directory, chowns it as self['_file_owner_uid'] """
        from os.path import isdir
        from os import mkdir

        self.logger.log(5, "Creating directory: %s" % path)
        if path.is_dir():
            path_dir = path.parent
            self.logger.debug("Directory path: %s" % path_dir)
        else:
            path_dir = path

        if not isdir(path_dir.parent):
            self.logger.debug("Parent directory does not exist: %s" % path_dir.parent)
            self._mkdir(path_dir.parent)

        if not isdir(path_dir):
            mkdir(path)
            self.logger.log(self['_build_log_level'], "Created directory: %s" % path)
        else:
            self.logger.debug("Directory already exists: %s" % path_dir)

        self._chown(path_dir)

    def _chown(self, path: Path) -> None:
        """ Chowns a file or directory as self['_file_owner_uid'] """
        from os import chown

        if path.owner() == self['_file_owner_uid'] and path.group() == self['_file_owner_uid']:
            self.logger.debug("File '%s' already owned by: %s" % (path, self['_file_owner_uid']))
            return

        chown(path, self['_file_owner_uid'], self['_file_owner_uid'])
        if path.is_dir():
            self.logger.debug("[%s] Set directory owner: %s" % (path, self['_file_owner_uid']))
        else:
            self.logger.debug("[%s] Set file owner: %s" % (path, self['_file_owner_uid']))

    def _write(self, file_name: Union[Path, str], contents: list[str], chmod_mask=0o644, in_build_dir=True) -> None:
        """
        Writes a file and owns it as self['_file_owner_uid']
        Sets the passed chmod
        """
        from os import chmod

        if in_build_dir:
            file_path = self._get_build_path(file_name)
        else:
            file_path = Path(file_name)

        if not file_path.parent.is_dir():
            self.logger.debug("Parent directory for '%s' does not exist: %s" % (file_path.name, file_path))
            self._mkdir(file_path.parent)

        if file_path.is_file():
            self.logger.warning("File already exists: %s" % file_path)
            if self.clean:
                self.logger.warning("Deleting file: %s" % file_path)
                file_path.unlink()

        self.logger.debug("[%s] Writing contents:\n%s" % (file_path, contents))
        with open(file_path, 'w') as file:
            file.writelines("\n".join(contents))

        self.logger.info("Wrote file: %s" % file_path)
        chmod(file_path, chmod_mask)
        self.logger.debug("[%s] Set file permissions: %s" % (file_path, chmod_mask))

        self._chown(file_path)

    def _copy(self, source: Union[Path, str], dest=None) -> None:
        """ Copies a file, chowns it as self['_file_owner_uid'] """
        from shutil import copy2

        if not isinstance(source, Path):
            source = Path(source)

        if not dest:
            self.logger.log(5, "No destination specified, using source: %s" % source)
            dest = source

        dest_path = self._get_build_path(dest)

        if not dest_path.parent.is_dir():
            self.logger.debug("Parent directory for '%s' does not exist: %s" % (dest_path.name, dest.parent))
            self._mkdir(dest_path.parent)

        if dest_path.is_file():
            self.logger.warning("File already exists: %s" % dest_path)
        elif dest_path.is_dir():
            self.logger.debug("Destination is a directory, adding source filename: %s" % source.name)
            dest_path = dest_path / source.name

        self.logger.log(self['_build_log_level'], "Copying '%s' to '%s'" % (source, dest_path))
        copy2(source, dest_path)

        self._chown(dest_path)

    def _symlink(self, source: Union[Path, str], target: Union[Path, str]) -> None:
        """ Creates a symlink """
        from os import symlink

        if not isinstance(source, Path):
            source = Path(source)

        target = self._get_build_path(target)

        if not target.parent.is_dir():
            self.logger.debug("Parent directory for '%s' does not exist: %s" % (target.name, target.parent))
            self._mkdir(target.parent)

        self.logger.debug("Creating symlink: %s -> %s" % (source, target))
        symlink(source, target)

    def _run(self, args: list[str]) -> CompletedProcess:
        """ Runs a command, returns the CompletedProcess object """
        self.logger.debug("Running command: %s" % ' '.join(args))
        cmd = run(args, capture_output=True)
        if cmd.returncode != 0:
            self.logger.error("Failed to run command: %s" % cmd.args)
            self.logger.error("Command output: %s" % cmd.stdout.decode())
            self.logger.error("Command error: %s" % cmd.stderr.decode())
            raise RuntimeError("Failed to run command: %s" % cmd.args)

        return cmd

    def _rotate_old(self, file_name: Path, sequence=0) -> None:
        """ Copies a file to file_name.old then file_nane.old.n, where n is the next number in the sequence """
        # Nothing to do if the file doesn't exist
        if not file_name.is_file():
            self.logger.debug("File does not exist: %s" % file_name)
            return

        # If the cycle count is not set, attempt to clean
        if not self.old_count:
            if self.clean:
                self.logger.warning("Deleting file: %s" % file_name)
                file_name.unlink()
                return
            else:
                # Fail if the cycle count is not set and clean is disabled
                raise RuntimeError("Unable to cycle file, as cycle count is not set and clean is disabled: %s" % file_name)

        self.logger.debug("[%d] Cycling file: %s" % (sequence, file_name))

        # If the sequence is 0, we're cycling the file for the first time, just rename it to .old
        suffix = '.old' if sequence == 0 else '.old.%d' % sequence
        target_file = file_name.with_suffix(suffix)

        self.logger.debug("[%d] Target file: %s" % (sequence, target_file))
        # If the target file exists, cycle again
        if target_file.is_file():
            # First check if we've reached the cycle limit
            if sequence >= self.old_count:
                # Clean the last file in the sequence if clean is enabled
                if self.clean:
                    self.logger.warning("Deleting old file: %s" % target_file)
                    target_file.unlink()
                else:
                    self.logger.debug("Cycle limit reached")
                    return
            else:
                self.logger.debug("[%d] Target file exists, cycling again" % sequence)
                self._rotate_old(target_file, sequence + 1)

        # Finally, rename the file
        self.logger.info("[%d] Cycling file: %s -> %s" % (sequence, file_name, target_file))
        file_name.rename(target_file)
