
__author__ = "desultory"
__version__ = "0.7.7"

from tomllib import load
from pathlib import Path
from subprocess import run

from ugrd.zen_custom import loggify, pretty_print
from ugrd.initramfs_dict import InitramfsConfigDict


@loggify
class InitramfsGenerator:
    def __init__(self, config='/etc/ugrd/config.toml', *args, **kwargs):
        self.config_filename = config
        self.build_pre = [self.generate_structure]
        self.config_dict = InitramfsConfigDict(logger=self.logger)

        # init_pre and init_final are run as part of generate_initramfs_main
        self.init_types = ['init_debug', 'init_early', 'init_main', 'init_late', 'init_premount', 'init_mount', 'init_cleanup']

        self.load_config()
        self.config_dict.verify_deps()
        self.config_dict.verify_mask()

    def load_config(self):
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
            self.config_dict[config] = value

        self.logger.debug("Loaded config: %s" % self.config_dict)

        for parameter in ['build_dir', 'out_dir', 'clean']:
            dict_value = self.config_dict[parameter]
            if dict_value is not None:
                setattr(self, parameter, dict_value)
            else:
                raise KeyError("Required parameter '%s' not found in config" % parameter)

    def clean_build_dir(self):
        """
        Cleans the build directory
        """
        from shutil import rmtree

        if not self.clean:
            raise ValueError("Clean is not set, not cleaning build dir: %s" % self.build_dir)

        if self.build_dir.is_dir():
            self.logger.warning("Cleaning build dir: %s" % self.build_dir)
            rmtree(self.build_dir)
        else:
            self.logger.info("Build dir is not present, not cleaning: %s" % self.build_dir)

    def build_structure(self):
        """
        builds the initramfs structure.
        Cleans the build dir first if clean is set
        """
        # If clean is set, clear the target build dir
        if self.clean:
            self.clean_build_dir()
        else:
            self.logger.debug("Not cleaning build dir: %s" % self.build_dir)

        self._run_hook('build_pre', return_output=False)
        self._run_hook('build_tasks', return_output=False)

    def _run_func(self, function, external=False, return_output=True):
        """
        Runs a function, returning the output in a list
        """
        self.logger.debug("Running function: %s" % function.__name__)
        if external:
            function_output = function(self)
        else:
            function_output = function()

        if not return_output:
            return []

        if function_output is not None:
            if isinstance(function_output, str):
                self.logger.debug("[%s] Function returned string: %s" % (function.__name__, function_output))
                return [function_output]
            else:
                self.logger.debug("[%s] Function returned output: %s" % (function.__name__, function_output))
                return function_output
        else:
            self.logger.warning("[%s] Function returned no output" % function.__name__)
            return []

    def _run_funcs(self, functions, external=False, return_output=True):
        """
        Runs a list of functions
        """
        self.logger.debug("Running functions: %s" % functions)
        out = []
        for function in functions:
            # Only append if returning the output
            if return_output:
                out += self._run_func(function, external=external, return_output=return_output)
            else:
                self._run_func(function, external=external, return_output=return_output)
        return out

    def _run_hook(self, hook, return_output=True):
        """
        Runs a hook for imported functions
        """
        out = []
        self.logger.info("Running hook: %s" % hook)
        if hasattr(self, hook):
            self.logger.debug("Running internal functions for hook: %s" % hook)
            out += self._run_funcs(getattr(self, hook), return_output=return_output)

        if external_functions := self.config_dict['imports'].get(hook):
            self.logger.debug("Running external functions for hook: %s" % hook)
            function_output = self._run_funcs(external_functions, external=True, return_output=return_output)
            out += function_output

        if return_output:
            self.logger.debug("[%s] Hook output: %s" % (hook, out))
            return out

    def _run_init_hook(self, level):
        """
        Runs the specified init hook, returning the output
        """
        out = ['\n\n# Begin %s' % level]
        out += self._run_hook(level)
        return out

    def generate_init_main(self):
        """
        Generates the main init file.
        Just runs each hook  in self.init_types and returns the output
        """
        out = []
        for init_type in self.init_types:
            hook = self._run_init_hook(init_type)
            # The hook will always contian a header, so check if it has any other output
            if len(hook) > 1:
                out.extend(hook)
            else:
                self.logger.warning("No output from init hook: %s" % init_type)
        return out

    def generate_init(self):
        """
        Generates the init file
        """
        self.logger.info("Running init generator functions")

        init = [self.config_dict['shebang']]

        init += ["# Generated by initramfs_generator.py v%s" % __version__]

        init.extend(self._run_init_hook('init_pre'))

        if self.config_dict['imports'].get('custom_init'):
            init += ["\n\n# !!custom_init"]
            init.extend(self._run_hook('custom_init'))
        else:
            init.extend(self.generate_init_main())

        init.extend(self._run_init_hook('init_final'))

        init += ["\n\n# END INIT"]

        self._write('init', init, 0o755)

        self.logger.debug("Final config:\n%s" % pretty_print(self.config_dict))

    def generate_structure(self):
        """
        Generates the initramfs directory structure
        """
        if not self.build_dir.is_dir():
            self._mkdir(self.build_dir)

        for subdir in set(self.config_dict['paths']):
            subdir_path = Path(subdir)
            subdir_relative_path = subdir_path.relative_to(subdir_path.anchor)
            target_dir = self.build_dir / subdir_relative_path

            self._mkdir(target_dir)

    def pack_build(self):
        """
        Packs the initramfs based on self.config_dict['imports']['pack']
        """
        if self.config_dict['imports'].get('pack'):
            self._run_hook('pack', return_output=False)
        else:
            self.logger.warning("No pack functions specified, the final build is present in: %s" % self.build_dir)

    def _mkdir(self, path):
        """
        Creates a directory, chowns it as self.config_dict['_file_owner_uid']
        """
        from os.path import isdir
        from os import mkdir

        self.logger.debug("Creating directory for: %s" % path)

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
            self.logger.info("Created directory: %s" % path)
        else:
            self.logger.debug("Directory already exists: %s" % path_dir)

        self._chown(path_dir)

    def _chown(self, path):
        """
        Chowns a file or directory as self.config_dict['_file_owner_uid']
        """
        from os import chown

        if path.owner() == self.config_dict['_file_owner_uid'] and path.group() == self.config_dict['_file_owner_uid']:
            self.logger.debug("File '%s' already owned by: %s" % (path, self.config_dict['_file_owner_uid']))
            return

        chown(path, self.config_dict['_file_owner_uid'], self.config_dict['_file_owner_uid'])
        if path.is_dir():
            self.logger.debug("[%s] Set directory owner: %s" % (path, self.config_dict['_file_owner_uid']))
        else:
            self.logger.debug("[%s] Set file owner: %s" % (path, self.config_dict['_file_owner_uid']))

    def _write(self, file_name, contents, chmod_mask=0o644, in_build_dir=True):
        """
        Writes a file and owns it as self.config_dict['_file_owner_uid']
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

        self.logger.debug("[%s] Writing contents:\n%s" % (file_path, pretty_print(contents)))
        with open(file_path, 'w') as file:
            file.writelines("\n".join(contents))

        self.logger.info("Wrote file: %s" % file_path)
        chmod(file_path, chmod_mask)
        self.logger.debug("[%s] Set file permissions: %s" % (file_path, chmod_mask))

        self._chown(file_path)

    def _copy(self, source, dest=None, in_build_dir=True):
        """
        Copies a file, chowns it as self.config_dict['_file_owner_uid']
        """
        from shutil import copy2

        if not isinstance(source, Path):
            source = Path(source)

        if not dest:
            self.logger.debug("No destination specified, using source: %s" % source)
            dest = source
        elif not isinstance(dest, Path):
            dest = Path(dest)

        if in_build_dir:
            dest_path = self._get_build_path(dest)
        else:
            dest_path = Path(dest)

        if not dest_path.parent.is_dir():
            self.logger.debug("Parent directory for '%s' does not exist: %s" % (dest_path.name, dest.parent))
            self._mkdir(dest_path.parent)

        if dest_path.is_file():
            self.logger.warning("File already exists: %s" % dest_path)
        elif dest_path.is_dir():
            self.logger.debug("Destination is a directory, adding source filename: %s" % source.name)
            dest_path = dest_path / source.name

        self.logger.info("Copying '%s' to '%s'" % (source, dest_path))
        copy2(source, dest_path)

        self._chown(dest_path)

    def _get_build_path(self, path):
        """
        Returns the build path
        """
        if not isinstance(path, Path):
            path = Path(path)

        if path.is_absolute():
            return self.build_dir / path.relative_to('/')
        else:
            return self.build_dir / path

    def _symlink(self, source, target, in_build_dir=True):
        """
        Creates a symlink
        """
        from os import symlink

        if not isinstance(source, Path):
            source = Path(source)

        if not isinstance(target, Path):
            target = Path(target)

        if in_build_dir:
            source = self._get_build_path(source)
            target = self._get_build_path(target)

        self.logger.debug("Creating symlink: %s -> %s" % (source, target))
        symlink(source, target)

    def _run(self, args):
        """
        Runs a command, returns the object
        """
        self.logger.debug("Running command: %s" % args)
        cmd = run(args, capture_output=True)
        if cmd.returncode != 0:
            self.logger.error("Failed to run command: %s" % cmd.args)
            self.logger.error("Command output: %s" % cmd.stdout.decode())
            self.logger.error("Command error: %s" % cmd.stderr.decode())
            raise RuntimeError("Failed to run command: %s" % cmd.args)

        return cmd

