# Copyright 2006-2025 Mark Diekhans
"""
pipettor interfaces to files and pipes, as well as some other IPC stuff.
"""
import os
import io
import errno
import queue
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
        self._exc = None
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
        try:
            self._readfn(self.read_fh.read())
        except Exception as ex:
            self._exc = ex

class DataReader(Dev):
    """Object to asynchronously read data from process into memory via a pipe.  A
    thread is use to prevent deadlock when both reading and writing to a child
    pipeline.

    Specifying binary access results in data of type bytes, otherwise str type
    is returned.  The buffering, encoding, and errors arguments are as used in
    the open() function.

    A reader maybe read from multiple process.
    """

    binary: bool
    "True if data is bytes, False if str"
    buffering: int
    "buffer size (-1 platform default, 0 unbuffered, 1 line-buffered)"
    encoding: "str | None"
    "text encoding name (None for the platform default)"
    errors: "str | None"
    "how decoding errors are handled (``strict``, ``replace``, ``backslashreplace``, ...)"
    newline: "str | None"
    "newline translation mode (None = universal, ``''`` = disabled, or a specific terminator)"

    def __init__(self, *, binary=False, buffering=-1, encoding=None, errors=None, newline=None):
        super().__init__()
        self.binary = binary
        self._threads = []
        self._buffer = []
        self._lock = threading.Lock()
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
        "close pipes and terminate thread; re-raise any exception from the reader thread"
        for thread in self._threads:
            thread.close()
        for thread in self._threads:
            if thread._exc is not None:
                exc = thread._exc
                thread._exc = None
                raise exc

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
    pipeline.

    ``data`` may be ``str``, ``bytes``, or an iterable yielding such
    items (e.g. a generator).  For ``str``/``bytes`` the type selects
    text vs binary.  For an iterable, pass ``binary=True`` for bytes.

    The buffering, encoding, and errors arguments are as used in
    the open() function.
    """

    def __init__(self, data, *, binary=False, buffering=-1, encoding=None, errors=None, newline=None):
        super().__init__()
        if isinstance(data, str):
            binary = False
            data = (data,)
        elif isinstance(data, bytes):
            binary = True
            data = (data,)
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
            for chunk in self._data:
                self._write_fh.write(chunk)
            self._write_fh.close()
            self._write_fh = None
        except IOError as ex:
            # don't raise error on broken pipe
            if ex.errno != errno.EPIPE:
                raise


class File(Dev):
    """A file path for input or output, used for specifying stdio associated
    with files. Mode is one of `r`, `w`, or `a`"""

    path: str
    "filesystem path of the file"
    mode: str
    "open mode, one of ``'r'``, ``'w'``, ``'a'``"

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


class _StreamDev(Dev, io.IOBase):
    """Shared base for :class:`StreamReader` and :class:`StreamWriter`.

    Provides a file-like parent-side endpoint of a pipe to a child
    process.  I/O is asynchronous, so the caller's reads and writes
    never have to keep up with the child and fully interleaved
    bidirectional use is safe from deadlock.

    ``max_queue`` caps the number of items buffered for the caller
    (``0`` = unbounded).  Set this only when the producer may vastly
    outrun the consumer and you want to bound buffered memory; the
    faster side will then block until the slower side catches up.
    """

    _EOF = object()

    binary: bool
    "True for bytes I/O, False for str"
    buffering: int
    "buffer size (-1 platform default, 0 unbuffered, 1 line-buffered)"
    encoding: "str | None"
    "text encoding name (None for the platform default)"
    errors: "str | None"
    "how encoding errors are handled (``strict``, ``replace``, ``backslashreplace``, ...)"
    newline: "str | None"
    "newline translation mode (None = universal, ``''`` = disabled, or a specific terminator)"
    max_queue: int
    "cap on items buffered for the caller (0 = unbounded)"

    def __init__(self, *, binary=False, buffering=-1, encoding=None, errors=None, newline=None, max_queue=0):
        super().__init__()
        self.binary = binary
        self.buffering = buffering
        self.encoding = encoding
        self.errors = errors
        self.newline = newline
        self.max_queue = max_queue
        self._process = None
        self._child_fd = None
        self._fh = None
        self._queue = queue.Queue(maxsize=max_queue)
        self._thread = None
        self._bridge_exc = None

    def _open_parent_fh(self, parent_fd, parent_mode):
        self._fh = open(parent_fd, parent_mode, buffering=self.buffering,
                        encoding=self.encoding, errors=self.errors, newline=self.newline)

    def _post_start_parent(self):
        if self._child_fd is not None:
            os.close(self._child_fd)
            self._child_fd = None
        self._thread = threading.Thread(target=self._bridge_loop,
                                        name=type(self).__name__ + "Bridge",
                                        daemon=True)
        self._thread.start()

    def _bridge_loop(self):
        raise NotImplementedError

    def _close_fh(self):
        if self._fh is not None:
            if not self._fh.closed:
                try:
                    self._fh.close()
                except BrokenPipeError:
                    pass
            self._fh = None
        if self._child_fd is not None:
            os.close(self._child_fd)
            self._child_fd = None

    def _raise_bridge_exc(self):
        if self._bridge_exc is not None:
            exc = self._bridge_exc
            self._bridge_exc = None
            raise exc

    @property
    def closed(self):
        # pre-bind state is not "closed" (so context-manager enter works
        # on an unbound device); once bound, track the underlying fh.
        if self._fh is None and self._process is None:
            return False
        return self._fh is None or self._fh.closed


class StreamReader(_StreamDev):
    """A file-like object for reading pipeline stdout in the parent.

    Bound as the ``stdout`` of a :class:`Pipeline`.  Use the standard
    file-like methods (``read``, ``readline``, ``__iter__``, ...) to
    consume the child's output.  Output is read asynchronously, so
    the child never blocks waiting for the caller to read.
    """

    _READ_CHUNK = 8192

    def __init__(self, *, binary=False, buffering=-1, encoding=None, errors=None, newline=None, max_queue=0):
        super().__init__(binary=binary, buffering=buffering, encoding=encoding,
                         errors=errors, newline=newline, max_queue=max_queue)
        self._residual = b'' if binary else ''

    def __str__(self):
        return "[StreamReader]"

    def _bind_write_to_process(self, process):
        if self._process is not None:
            raise PipettorException("StreamReader already bound to a process")
        self._process = process
        parent_fd, self._child_fd = os.pipe()
        self._open_parent_fh(parent_fd, "rb" if self.binary else "r")

    def get_child_write_fd(self, process):
        assert process is self._process
        return self._child_fd

    def _bridge_loop(self):
        "drain the pipe into the queue; terminates on EOF or fh close"
        try:
            while True:
                if self.binary:
                    chunk = self._fh.read1(self._READ_CHUNK)
                else:
                    chunk = self._fh.readline()
                if not chunk:
                    break
                self._queue.put(chunk)
        except BrokenPipeError:
            pass  # normal EOF
        except ValueError as ex:
            # benign: fh was closed under us during shutdown.
            # real problems (e.g. UnicodeDecodeError, a ValueError subclass)
            # happen while the fh is still open — propagate those.
            if self._fh is not None and not self._fh.closed:
                self._bridge_exc = ex
        except Exception as ex:
            self._bridge_exc = ex
        finally:
            self._queue.put(self._EOF)

    def close(self):
        # fh close makes the bridge loop exit; then join.
        self._close_fh()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self._raise_bridge_exc()

    def readable(self):
        return True

    def writable(self):
        return False

    def read(self, size=-1):
        empty = b'' if self.binary else ''
        parts = [self._residual] if self._residual else []
        total = len(self._residual)
        self._residual = empty
        while size < 0 or total < size:
            item = self._queue.get()
            if item is self._EOF:
                self._queue.put(self._EOF)   # keep sentinel for future reads
                break
            parts.append(item)
            total += len(item)
        combined = empty.join(parts)
        if size >= 0 and len(combined) > size:
            self._residual = combined[size:]
            combined = combined[:size]
        return combined

    def readline(self, size=-1):
        empty = b'' if self.binary else ''
        sep = b'\n' if self.binary else '\n'
        buf = self._residual
        self._residual = empty
        while sep not in buf:
            if size >= 0 and len(buf) >= size:
                break
            item = self._queue.get()
            if item is self._EOF:
                self._queue.put(self._EOF)
                break
            buf += item
        if sep in buf:
            idx = buf.index(sep) + 1
        else:
            idx = len(buf)
        if size >= 0 and idx > size:
            idx = size
        line, self._residual = buf[:idx], buf[idx:]
        return line

    def readlines(self, hint=-1):
        lines = []
        while True:
            line = self.readline()
            if not line:
                break
            lines.append(line)
        return lines

    def __iter__(self):
        while True:
            line = self.readline()
            if not line:
                return
            yield line

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line


class StreamWriter(_StreamDev):
    """A file-like object for writing to pipeline stdin in the parent.

    Bound as the ``stdin`` of a :class:`Pipeline`.  Use the standard
    file-like methods (``write``, ``writelines``) to send data to the
    child.  Writes are forwarded asynchronously, so the caller never
    blocks waiting for the child to read.

    Call :meth:`close` after the last write to send EOF to the child.
    """

    def __str__(self):
        return "[StreamWriter]"

    def _bind_read_to_process(self, process):
        if self._process is not None:
            raise PipettorException("StreamWriter already bound to a process")
        self._process = process
        self._child_fd, parent_fd = os.pipe()
        self._open_parent_fh(parent_fd, "wb" if self.binary else "w")

    def get_child_read_fd(self, process):
        assert process is self._process
        return self._child_fd

    def _bridge_loop(self):
        """drain the queue into the pipe; terminates on EOF sentinel.

        Each item is flushed to the kernel pipe immediately so that an
        interleaved reader sees the bytes as soon as they're produced,
        regardless of the parent-side fh's buffering mode."""
        try:
            while True:
                item = self._queue.get()
                if item is self._EOF:
                    break
                try:
                    self._fh.write(item)
                    self._fh.flush()
                except BrokenPipeError:
                    # child closed stdin; discard remainder
                    self._drain_queue_after_broken_pipe()
                    return
        except Exception as ex:
            self._bridge_exc = ex
        finally:
            try:
                if self._fh is not None and not self._fh.closed:
                    self._fh.flush()
            except Exception:
                pass

    def _drain_queue_after_broken_pipe(self):
        while True:
            item = self._queue.get()
            if item is self._EOF:
                return

    def close(self):
        if self._thread is not None and self._thread.is_alive():
            self._queue.put(self._EOF)
            self._thread.join()
            self._thread = None
        self._close_fh()
        self._raise_bridge_exc()

    def readable(self):
        return False

    def writable(self):
        return True

    def write(self, data):
        if self._fh is None:
            raise ValueError("write to closed StreamWriter")
        self._queue.put(data)
        return len(data)

    def writelines(self, lines):
        for line in lines:
            self.write(line)


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
