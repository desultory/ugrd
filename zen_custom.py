"""
A collection of classes and decorators
"""
__version__ = '2.7.0'
__author__ = 'desultory'

import logging
from sys import modules
from threading import Thread, Event
from queue import Queue


def update_init(decorator):
    """
    Updates the init function of a class
    puts the decorated function at the end of the init
    """
    def decorator_wrapper(cls):
        original_init = cls.__init__

        def new_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            decorator(self)

        cls.__init__ = new_init
        return cls
    return decorator_wrapper


def handle_plural(function):
    """
    Wraps functions to take a list/dict and iterate over it
    the last argument should be iterable
    """
    def wrapper(self, *args):
        if len(args) == 1:
            focus_arg = args[0]
            other_args = tuple()
        else:
            focus_arg = args[-1]
            other_args = args[:-1]

        if isinstance(focus_arg, list) and not isinstance(focus_arg, str):
            for item in focus_arg:
                function(self, *(other_args + (item,)))
        elif isinstance(focus_arg, dict):
            for key, value in focus_arg.items():
                function(self, *(other_args + (key, value,)))
        else:
            self.logger.debug("Arguments were not expanded: %s" % args)
            function(self, *args)
    return wrapper


def threaded(function):
    """
    Simply starts a function in a thread
    Adds it to an internal _threads list for handling
    """
    def wrapper(self, *args, **kwargs):
        if not hasattr(self, '_threads'):
            self._threads = list()

        thread_exception = Queue()

        def exception_wrapper(*args, **kwargs):
            try:
                function(*args, **kwargs)
            except Exception as e:
                self.logger.warning("Exception in thread: %s" % function.__name__)
                thread_exception.put(e)
                self.logger.debug(e)

        thread = Thread(target=exception_wrapper, args=(self, *args), kwargs=kwargs, name=function.__name__)
        thread.start()
        self._threads.append((thread, thread_exception))
    return wrapper


def add_thread(name, target, description=None):
    """
    Adds a thread of a class which targets the target
    Creates a dict that contains the name of the thread as a key, with the thread as a value
    Cteates basic helper functions to manage the thread
    """
    def decorator(cls):
        def create_thread(self):
            if not hasattr(self, 'threads'):
                self.threads = dict()

            if "." in target:
                target_parts = target.split(".")
                target_attr = self
                for part in target_parts:
                    target_attr = getattr(target_attr, part)
            else:
                target_attr = getattr(self, target)

            self.threads[name] = Thread(target=target_attr, name=description)
            self.logger.info("Created thread: %s" % name)

        def start_thread(self):
            thread = self.threads[name]
            setattr(self, f"_stop_processing_{name}", Event())
            if thread._is_stopped:
                self.logger.info("Re-creating thread")
                getattr(self, f"create_{name}_thread")()
                thread = self.threads[name]

            if thread._started.is_set() and not thread._is_stopped:
                self.logger.warning("%s thread is already started" % name)
            else:
                self.logger.info("Starting thread: %s" % name)
                thread.start()
                return True

        def stop_thread(self):
            thread = self.threads[name]
            dont_join = False
            if not thread._started.is_set() or thread._is_stopped:
                self.logger.warning("Thread is not active: %s" % name)
                dont_join = True

            if hasattr(self, f"_stop_processing_{name}"):
                self.logger.debug("Setting stop event for thread: %s" % name)
                getattr(self, f"_stop_processing_{name}").set()

            if hasattr(self, f"stop_{name}_thread_actions"):
                self.logger.debug("Calling: %s" % f"stop_{name}_thread_actions")
                getattr(self, f"stop_{name}_thread_actions")()

            if hasattr(self, f"_{name}_timer"):
                self.logger.info("Stopping the timer for thread: %s" % name)
                getattr(self, f"_{name}_timer").cancel()

            if not dont_join:
                self.logger.info("Waiting on thread to end: %s" % name)
                thread.join()
            return True

        setattr(cls, f"create_{name}_thread", create_thread)
        setattr(cls, f"start_{name}_thread", start_thread)
        setattr(cls, f"stop_{name}_thread", stop_thread)

        return update_init(create_thread)(cls)
    return decorator


def thread_wrapped(thread_name):
    """
    Wrap a class function to be used with add_thread
    """
    def decorator(function):
        def wrapper(self, *args, **kwargs):
            self.logger.info("Starting the processing loop for thread: %s" % thread_name)
            while not getattr(self, f"_stop_processing_{thread_name}").is_set():
                function(self, *args, **kwargs)
            self.logger.info("The processing loop has ended for thread: %s" % thread_name)
        return wrapper
    return decorator


def loggify(cls):
    """
    Decorator for classes to add a logging object and log basic tasks
    """
    class ClassWrapper(cls):
        def __init__(self, *args, **kwargs):
            parent_logger = kwargs.pop('logger') if isinstance(kwargs.get('logger'), logging.Logger) else logging.getLogger()
            self.logger = parent_logger.getChild(self.__class__.__name__)
            self.logger.setLevel(self.logger.parent.level)

            def has_handler(logger):
                parent = logger
                while parent:
                    if parent.handlers:
                        return True
                    parent = parent.parent
                return False

            if not has_handler(self.logger):
                color_stream_handler = logging.StreamHandler()
                color_stream_handler.setFormatter(ColorLognameFormatter(fmt='%(levelname)s | %(name)-42s | %(message)s'))
                self.logger.addHandler(color_stream_handler)
                self.logger.info("Adding default handler: %s" % self.logger)

            if kwargs.get('_log_init', True) is True:
                self.logger.info("Intializing class: %s" % cls.__name__)

                if args:
                    self.logger.debug("Args: %s" % repr(args))
                if kwargs:
                    self.logger.debug("Kwargs: %s" % repr(kwargs))
                if module_version := getattr(modules[cls.__module__], '__version__', None):
                    self.logger.info("Module version: %s" % module_version)
                if class_version := getattr(cls, '__version__', None):
                    self.logger.info("Class version: %s" % class_version)
            else:
                self.logger.log(5, "Init debug logging disabled for: %s" % cls.__name__)

            super().__init__(*args, **kwargs)

        def __setattr__(self, name, value):
            super().__setattr__(name, value)
            if not isinstance(self.logger, logging.Logger):
                raise ValueError("The logger is not defined")

            if isinstance(value, list) or isinstance(value, dict) or isinstance(value, str) and "\n" in value:
                self.logger.log(5, "Set '%s' to:\n%s" % (name, value))
            else:
                self.logger.log(5, "Set '%s' to: %s" % (name, value))

    ClassWrapper.__name__ = cls.__name__
    ClassWrapper.__module__ = cls.__module__
    ClassWrapper.__qualname__ = cls.__qualname__

    return ClassWrapper


class ColorLognameFormatter(logging.Formatter):
    """
    ColorLognameFormatter Class
    Add the handler to the stdout handler using:
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(ColorLognameFormatter())
    """

    _level_str_len = 8
    # Define the color codes
    _reset_str = '\x1b[0m'
    _grey_str = '\x1b[37m'
    _blue_str = '\x1b[34m'
    _yllw_str = '\x1b[33m'
    _sred_str = '\x1b[31m'
    _bred_str = '\x1b[31;1m'
    _magenta_str = '\x1b[35m'
    # Make the basic strings
    _debug_color_str = f"{_grey_str}DEBUG{_reset_str}".ljust(
        _level_str_len + len(_reset_str) + len(_grey_str), ' ')
    _info_color_str = f"{_blue_str}INFO{_reset_str}".ljust(
        _level_str_len + len(_reset_str) + len(_blue_str), ' ')
    _warn_color_str = f"{_yllw_str}WARNING{_reset_str}".ljust(
        _level_str_len + len(_reset_str) + len(_yllw_str), ' ')
    _error_color_str = f"{_sred_str}ERROR{_reset_str}".ljust(
        _level_str_len + len(_reset_str) + len(_sred_str), ' ')
    _crit_color_str = f"{_bred_str}CRITICAL{_reset_str}".ljust(
        _level_str_len + len(_reset_str) + len(_bred_str), ' ')
    # Format into a dict
    _color_levelname = {'DEBUG': _debug_color_str,
                        'INFO': _info_color_str,
                        'WARNING': _warn_color_str,
                        'ERROR': _error_color_str,
                        'CRITICAL': _crit_color_str}

    def __init__(self, fmt='%(levelname)s | %(message)s', *args, **kwargs):
        super().__init__(fmt, *args, **kwargs)

    def format(self, record):
        # When calling format, replace the levelname with a colored version
        # Note: the string size is greatly increased because of the color codes
        old_levelname = record.levelname
        if record.levelname in self._color_levelname:
            record.levelname = self._color_levelname[record.levelname]
        else:
            record.levelname = f"{self._magenta_str}{record.levelname}{self._reset_str}".ljust(
                self._level_str_len + len(self._magenta_str) + len(self._reset_str), ' ')

        format_str = super().format(record)

        try:
            record.levelname = old_levelname
        except NameError:
            pass

        return format_str


@loggify
class NoDupFlatList(list):
    """
    List that automatically filters duplicate elements when appended and concatenated
    """
    __version__ = "0.2.0"

    def __init__(self, no_warn=False, log_bump=0, *args, **kwargs):
        self.no_warn = no_warn
        self.logger.setLevel(self.logger.parent.level + log_bump)

    @handle_plural
    def append(self, item):
        if item not in self:
            self.logger.debug("Adding list item: %s" % item)
            super().append(item)
        elif not self.no_warn:
            self.logger.warning("List item already exists: %s" % item)

    def __iadd__(self, item):
        self.append(item)
        return self

