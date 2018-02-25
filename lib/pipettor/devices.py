# Copyright 2006-2015 Mark Diekhans
"""
pipettor interfaces to files and pipes, as well as some other IPC stuff.
"""
from __future__ import print_function
import six
import os
import re
import fcntl
import errno
import threading
import pickle
from pipettor.exceptions import PipettorException


# note:
# A problem with python threads and signal handling is that SIGINT (C-c) will
# not raise an exception if it's blocked in thread join.  If the thread never
# terminates, the process hangs, not responding to SIGINT.  This can happen if
# the forked process is hung.  to work around this, setting the I/O threads to
# daemon solves the problem.  It also cause the process to to wait if the main
# process exists and close hasn't been called.
#
#  http://bugs.python.org/issue21822
#  http://code.activestate.com/recipes/496735-workaround-for-missed-sigint-in-multithreaded-prog/


_rwa_re = re.compile("^[rwa]b?$")
_rw_re = re.compile("^[rw]b?$")


def _validate_mode(mode, allow_append):
    mode_re = _rwa_re if allow_append else _rw_re
    if mode_re.match(mode) is None:
        expect = "'r', 'w', or 'a'" if allow_append else "'r' or 'w'"
        raise PipettorException("invalid mode: '{}', expected {} with optional 'b' suffix".format(mode, expect))


def _open_compat(fd_or_path, mode, buffering=-1, encoding=None, errors=None):
    """PY2/3 compatibility wrapper for open/fdopen"""
    if six.PY3:
        return open(fd_or_path, mode, buffering=buffering, encoding=encoding, errors=errors)
    elif isinstance(fd_or_path, int):
        return os.fdopen(fd_or_path, mode, buffering)
    else:
        return open(fd_or_path, mode, buffering)


class Dev(object):
    """Base class for objects specifying process input or output.  They
    provide a way of hide details of setting up interprocess
    communication.

    Derived class implement the following properties, if applicable:
       read_fd - file integer descriptor for reading
       read_fh - file object for reading
       write_fd - file integer descriptor for writing
       write_fh - file object for writing"""

    def _bind_read_to_process(self, process):
        """associate read side with child process."""
        pass

    def _bind_write_to_process(self, process):
        """associate write side with child process."""
        pass

    def _bind_to_process(self, process, mode):
        """associate with a child process based on mode"""
        if mode.startswith("r"):
            self._bind_read_to_process(process)
        else:
            self._bind_write_to_process(process)

    def _post_fork_parent(self):
        """post-fork parent setup."""
        pass

    def _post_fork_child(self):
        """post-fork child setup."""
        pass

    def _post_exec_parent(self):
        "called do any post-exec handling in the parent"
        pass

    def close(self):
        """close the device"""
        pass


class DataReader(Dev):
    """Object to asynchronously read data from process into memory via a pipe.  A
    thread is use to prevent deadlock when both reading and writing to a child
    pipeline.

    For Python3, specifying binary results in data of type bytes, otherwise
    str.  The buffering, encoding, and errors arguments are as used in the
    Python 3 open() function.  With Python 2, encoding and error is ignored.
    """
    def __init__(self, binary=False, buffering=-1, encoding=None, errors=None):
        super(DataReader, self).__init__()
        self.binary = binary
        self._process = None
        self._buffer = []
        self._thread = None
        self.read_fh = self.write_fd = None
        read_fd, self.write_fd = os.pipe()
        mode = "rb" if binary else "r"
        self.read_fh = _open_compat(read_fd, mode, buffering, encoding, errors)

    def __str__(self):
        return "[DataReader]"

    def _bind_write_to_process(self, process):
        """associate write side with child process."""
        if self._process is not None:
            raise PipettorException("DataReader already bound to a process")
        self._process = process

    def _post_fork_parent(self):
        """post-fork parent setup."""
        os.close(self.write_fd)
        self.write_fd = None

    def _post_fork_child(self):
        """post-fork child setup."""
        self.read_fh.close()

    def _post_exec_parent(self):
        "called to do any post-exec handling in the parent"
        self._thread = threading.Thread(target=self._reader)
        self._thread.daemon = True  # see note at top of this file
        self._thread.start()

    def close(self):
        "close pipes and terminate thread"
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self.read_fh is not None:
            self.read_fh.close()
            self.read_fh = None
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None

    def _reader(self):
        "child read thread function"
        assert self.write_fd is None
        self._buffer.append(self.read_fh.read())

    @property
    def data(self):
        "return buffered data as a string or bytes"
        if self.binary:
            return b"".join(self._buffer)
        else:
            return "".join(self._buffer)


class DataWriter(Dev):
    """Object to asynchronously write data to process from memory via a pipe.  A
    thread is use to prevent deadlock when both reading and writing to a child
    pipeline.  Text or binary output is determined by the type of data.

    For Python3, binary results in data of type bytes, otherwise str.  The
    buffering, encoding, and errors arguments are as used in the Python 3
    open() function. With Python 2, encoding and error is ignored.
    """

    def __init__(self, data, buffering=-1, encoding=None, errors=None):
        super(DataWriter, self).__init__()
        binary = not isinstance(data, six.string_types)
        self._data = data
        self._thread = None
        self._process = None
        self.read_fd = self.write_fh = None
        self.read_fd, write_fd = os.pipe()
        mode = "wb" if binary else "w"
        self.write_fh = _open_compat(write_fd, mode, buffering, encoding, errors)

    def __str__(self):
        return "[DataWriter]"

    def _bind_read_to_process(self, process):
        """associate write side with child process."""
        if self._process is not None:
            raise PipettorException("DataWriter already bound to a process")
        self._process = process

    def _post_fork_parent(self):
        """post-fork parent setup."""
        os.close(self.read_fd)
        self.read_fd = None

    def _post_fork_child(self):
        """post-fork child setup."""
        self.write_fh.close()
        self.write_fh = None

    def _post_exec_parent(self):
        "called to do any post-exec handling in the parent"
        self._thread = threading.Thread(target=self._writer)
        self._thread.daemon = True  # see note at top of this file
        self._thread.start()

    def close(self):
        "close pipes and terminate thread"
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self.read_fd is not None:
            os.close(self.read_fd)
            self.read_fd = None
        if self.write_fh is not None:
            self.write_fh.close()
            self.write_fh = None

    def _writer(self):
        "write thread function"
        assert self.read_fd is None
        try:
            self.write_fh.write(self._data)
            self.write_fh.close()
            self.write_fh = None
        except IOError as ex:
            # don't raise error on broken pipe
            if ex.errno != errno.EPIPE:
                raise


class File(Dev):
    """A file path for input or output, used for specifying stdio associated
    with files. Mode starts with standard r, w, or a"""

    def __init__(self, path, mode="r"):
        super(File, self).__init__()
        self._path = path
        self._mode = mode
        # only one of the file descriptors is ever opened
        self.read_fd = self.write_fd = None
        _validate_mode(mode, allow_append=True)
        if self._mode[0] == 'r':
            self.read_fd = os.open(self._path, os.O_RDONLY)
        elif self._mode[0] == 'w':
            self.write_fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        else:
            self.write_fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)

    def __str__(self):
        return self._path

    def close(self):
        "close file if open"
        if self.read_fd is not None:
            os.close(self.read_fd)
            self.read_fd = None
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None

    def _post_fork_parent(self):
        """post-fork child setup."""
        self.close()


class _SiblingPipe(Dev):
    """Interprocess communication between two child process by anonymous
    pipes."""

    def __init__(self):
        super(_SiblingPipe, self).__init__()
        self.read_fd, self.write_fd = os.pipe()

    def __str__(self):
        return "[Pipe]"

    def _post_exec_parent(self):
        "called to do any post-exec handling in the parent"
        os.close(self.read_fd)
        self.read_fd = None
        os.close(self.write_fd)
        self.write_fd = None

    def close(self):
        if self.read_fd is not None:
            os.close(self.read_fd)
            self.read_fd = None
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None


class _StatusPipe(object):
    """One-way communicate from parent and child during setup.  Close-on-exec is set,
    so the pipe closing without any data being written indicates a successful exec."""
    __slots__ = ("read_fh", "write_fh")

    def __init__(self):
        read_fd, write_fd = os.pipe()
        self.read_fh = _open_compat(read_fd, "rb")
        self.write_fh = _open_compat(write_fd, "wb")
        try:
            self._set_close_on_exec(self.write_fh)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _set_close_on_exec(fh):
        flags = fcntl.fcntl(fh.fileno(), fcntl.F_GETFD)
        fcntl.fcntl(fh.fileno(), fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)

    def close(self):
        "close pipes if open"
        if self.read_fh is not None:
            self.read_fh.close()
            self.read_fh = None
        if self.write_fh is not None:
            self.write_fh.close()
            self.write_fh = None

    def _post_fork_parent(self):
        "post fork handling in parent"
        self.write_fh.close()
        self.write_fh = None

    def _post_fork_child(self):
        "post fork handling in child"
        self.read_fh.close()
        self.read_fh = None

    def send(self, obj):
        """send an object"""
        pickle.dump(obj, self.write_fh)
        self.write_fh.flush()

    def receive(self):
        """receive object from the child or None on EOF"""
        try:
            return pickle.load(self.read_fh)
        except EOFError:
            return None
