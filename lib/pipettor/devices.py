# Copyright 2006-2015 Mark Diekhans
"""
pipettor interfaces to files and pipes, as well as some other IPC stuff.
"""
import os
import errno
import threading
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

    def _post_start_parent(self):
        "called do any post-exec handling in the parent"
        pass

    def close(self):
        """close the device"""
        pass


class DataReader(Dev):
    """Object to asynchronously read data from process into memory via a pipe.  A
    thread is use to prevent deadlock when both reading and writing to a child
    pipeline.

    Specifying binary access results in data of type bytes, otherwise str type
    is returned.  The buffering, encoding, and errors arguments are as used in
    the open() function.
    """
    def __init__(self, *, binary=False, buffering=-1, encoding=None, errors=None):
        super(DataReader, self).__init__()
        self.binary = binary
        self._process = None
        self._buffer = []
        self._thread = None
        self.read_fh = self.write_fd = None
        read_fd, self.write_fd = os.pipe()
        mode = "rb" if binary else "r"
        self.read_fh = open(read_fd, mode, buffering=buffering, encoding=encoding, errors=errors)

    def __str__(self):
        return "[DataReader]"

    def _bind_write_to_process(self, process):
        """associate write side with child process."""
        if self._process is not None:
            raise PipettorException("DataReader already bound to a process")
        self._process = process

    def _post_start_parent(self):
        "called to do any post-start handling in the parent"
        os.close(self.write_fd)
        self.write_fd = None

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

    The buffering, encoding, and errors arguments are as used in
    the open() function.
    """

    def __init__(self, data, *, buffering=-1, encoding=None, errors=None):
        super(DataWriter, self).__init__()
        binary = not isinstance(data, str)
        self._data = data
        self._thread = None
        self._process = None
        self.read_fd = self.write_fh = None
        self.read_fd, write_fd = os.pipe()
        mode = "wb" if binary else "w"
        self.write_fh = open(write_fd, mode, buffering=buffering, encoding=encoding, errors=errors)

    def __str__(self):
        return "[DataWriter]"

    def _bind_read_to_process(self, process):
        """associate write side with child process."""
        if self._process is not None:
            raise PipettorException("DataWriter already bound to a process")
        self._process = process

    def _post_start_parent(self):
        "called to do any start-exec handling in the parent"
        os.close(self.read_fd)
        self.read_fd = None

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
    with files. Mode is invalued on of standard r, w, or a"""

    def __init__(self, path, mode="r"):
        super(File, self).__init__()
        self.path = path
        self.mode = mode
        # only one of the file descriptors is ever opened
        self.read_fd = self.write_fd = None
        if mode.find('r') >= 0:
            self.read_fd = os.open(self.path, os.O_RDONLY)
        elif mode.find('w') >= 0:
            self.write_fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        elif mode.find('a') >= 0:
            self.write_fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
        else:
            raise PipettorException("invalid or unsupported mode '{}' opening {}".format(mode, path))

    def __str__(self):
        return self.path

    def close(self):
        "close file if open"
        if self.read_fd is not None:
            os.close(self.read_fd)
            self.read_fd = None
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None

    def _post_start_parent(self):
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

    def _post_start_parent(self):
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
