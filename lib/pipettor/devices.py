# Copyright 2006-2025 Mark Diekhans
"""
pipettor interfaces to files and pipes, as well as some other IPC stuff.
"""
import os
import errno
import threading
from pipettor.exceptions import PipettorException


class Dev:
    """Base class for objects specifying process input or output.  They
    provide a way of hide details of setting up interprocess
    communication.
    """

    def get_child_write_fd(self, process):
        """get write-to fileno for specified process associated with this device"""
        raise NotImplementedError('get_child_write_fd')

    def get_child_read_fd(self, process):
        """get read-fromo fileno for specified process associated with this device"""
        raise NotImplementedError('get_child_read_fd')

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

class _ReaderThread:
    """thread and pipe associated with DataReader.
    this is a separate class to allow for multiple
    process that write to stderr"""
    def __init__(self, process, readfn, binary, buffering, encoding, errors, newline):
        self.process = process
        self._readfn = readfn
        self._thread = None
        self.read_fh = self.write_fd = None
        read_fd, self.write_fd = os.pipe()
        mode = "rb" if binary else "r"
        self.read_fh = open(read_fd, mode, buffering=buffering,
                            encoding=encoding, errors=errors, newline=newline)

    def post_start_parent(self):
        "called to do any post-start handling in the parent"
        os.close(self.write_fd)
        self.write_fd = None

        self._thread = threading.Thread(target=self._reader, daemon=True)
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
        self._readfn(self.read_fh.read())

class DataReader(Dev):
    """Object to asynchronously read data from process into memory via a pipe.  A
    thread is use to prevent deadlock when both reading and writing to a child
    pipeline.

    Specifying binary access results in data of type bytes, otherwise str type
    is returned.  The buffering, encoding, and errors arguments are as used in
    the open() function.

    A reader maybe read from multiple process.
    """
    def __init__(self, *, binary=False, buffering=-1, encoding=None, errors=None, newline=None):
        super().__init__()
        self.binary = binary
        self._threads = []
        self._buffer = []
        self._lock = threading.Lock()
        self.binary = binary
        self.buffering = buffering
        self.encoding = encoding
        self.errors = errors
        self.newline = newline

    def __str__(self):
        return "[DataReader]"

    def _bind_read_to_process(self, process):
        """associate read side with child process."""
        raise NotImplementedError('DataReader._bind_read_to_process')

    def _bind_write_to_process(self, process):
        """associate write side with child process."""
        thread = _ReaderThread(process, self._readfn, self.binary, self.buffering,
                               self.encoding, self.errors, self.newline)
        self._threads.append(thread)

    def _post_start_parent(self):
        for thread in self._threads:
            thread.post_start_parent()

    def close(self):
        "close pipes and terminate thread"
        for thread in self._threads:
            thread.close()

    def _readfn(self, data):
        "store to buffer"
        with self._lock:
            self._buffer.append(data)

    def get_child_write_fd(self, process):
        for thread in self._threads:
            if process is thread.process:
                return thread.write_fd
        raise ValueError("process not associated with this device")

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

    def __init__(self, data, *, buffering=-1, encoding=None, errors=None, newline=None):
        super().__init__()
        binary = not isinstance(data, str)
        self._data = data
        self._thread = None
        self._process = None
        self._read_fd = self._write_fh = None
        self._read_fd, write_fd = os.pipe()
        mode = "wb" if binary else "w"
        self._write_fh = open(write_fd, mode, buffering=buffering,
                              encoding=encoding, errors=errors, newline=newline)

    def __str__(self):
        return "[DataWriter]"

    def _bind_read_to_process(self, process):
        """associate write side with child process."""
        if self._process is not None:
            raise PipettorException("DataWriter already bound to a process")
        self._process = process

    def _bind_write_to_process(self, process):
        """associate write side with child process."""
        raise NotImplementedError('_bind_write_to_process')

    def _post_start_parent(self):
        "called to do any start-exec handling in the parent"
        os.close(self._read_fd)
        self._read_fd = None
        self._thread = threading.Thread(target=self._writer, daemon=True)
        self._thread.start()

    def get_child_read_fd(self, process):
        assert process is self._process
        return self._read_fd

    def close(self):
        "close pipes and terminate thread"
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self._read_fd is not None:
            os.close(self._read_fd)
            self._read_fd = None
        if self._write_fh is not None:
            self._write_fh.close()
            self._write_fh = None

    def _writer(self):
        "write thread function"
        assert self._read_fd is None
        try:
            self._write_fh.write(self._data)
            self._write_fh.close()
            self._write_fh = None
        except IOError as ex:
            # don't raise error on broken pipe
            if ex.errno != errno.EPIPE:
                raise


class File(Dev):
    """A file path for input or output, used for specifying stdio associated
    with files. Mode is one of `r`, `w`, or `a`"""

    def __init__(self, path, mode="r"):
        super().__init__()
        self.path = path
        self.mode = mode
        # only one of the file descriptors is ever opened
        self._read_fd = self._write_fd = None
        if mode.find('r') >= 0:
            self._read_fd = os.open(self.path, os.O_RDONLY)
        elif mode.find('w') >= 0:
            self._write_fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        elif mode.find('a') >= 0:
            self._write_fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
        else:
            raise PipettorException("invalid or unsupported mode '{}' opening {}".format(mode, path))

    def __str__(self):
        return self.path

    def get_child_write_fd(self, process):
        assert self._write_fd is not None
        return self._write_fd

    def get_child_read_fd(self, process):
        assert self._read_fd is not None
        return self._read_fd

    def _post_start_parent(self):
        """post-fork child setup."""
        self.close()

    def close(self):
        "close file if open"
        if self._read_fd is not None:
            os.close(self._read_fd)
            self._read_fd = None
        if self._write_fd is not None:
            os.close(self._write_fd)
            self._write_fd = None


class _SiblingPipe(Dev):
    """Interprocess communication between two child process by anonymous
    pipes."""

    def __init__(self):
        super().__init__()
        self._read_fd, self._write_fd = os.pipe()

    def __str__(self):
        return "[Pipe]"

    def get_child_write_fd(self, process):
        return self._write_fd

    def get_child_read_fd(self, process):
        return self._read_fd

    def _post_start_parent(self):
        "called to do any post-exec handling in the parent"
        os.close(self._read_fd)
        self._read_fd = None
        os.close(self._write_fd)
        self._write_fd = None

    def close(self):
        if self._read_fd is not None:
            os.close(self._read_fd)
            self._read_fd = None
        if self._write_fd is not None:
            os.close(self._write_fd)
            self._write_fd = None
