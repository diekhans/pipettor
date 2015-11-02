# Copyright 2015 Mark Diekhans
"""
pipettor interfaces to files and pipes, as well as some other IPC stuff.
"""
from __future__ import print_function
import os
import re
import fcntl
import stat
import errno
import threading
import pickle
from cStringIO import StringIO
from pipettor.exceptions import PipettorException

_rwa_re = re.compile("^[rwa]b?$")
_rw_re = re.compile("^[rw]b?$")
def _validate_mode(mode, allow_append):
    mode_re = _rwa_re if allow_append else _rw_re
    if mode_re.match(mode) is None:
        expect = "'r', 'w', or 'a'" if allow_append else "'r' or 'w'"
        raise PipettorException("invalid mode: '%s', expected %s with optional 'b' suffix" % (mode, expect))

class Dev(object):
    """Base class for objects specifying process input or output.  They
    provide a way of hide details of setting up interprocess
    communication.

    Derived class implement the following properties, if applicable:
       read_fd - file integer descriptor for reading
       read_fh - file object for reading
       write_fd - file integer descriptor for writing
       write_fh - file object for writing"""

    def post_fork_parent(self):
        """post-fork parent setup."""
        pass

    def post_fork_child(self):
        """post-fork child setup."""
        pass

    def post_exec_parent(self):
        "called do any post-exec handling in the parent"
        pass
        
    def close(self):
        """close the device"""
        pass

class DataReader(Dev):
    """Object to asynchronously read data from process into memory via a pipe.  A
    thread is use to prevent deadlock when both reading and writing to a child
    pipeline.
    """
    # FIXME: show DataReader object be passable to multiple process?
    # FIXME make sure it can handled binary data
    def __init__(self):
        Dev.__init__(self)
        read_fd, self.write_fd = os.pipe()
        self.read_fh = os.fdopen(read_fd, "rb")
        self.__buffer = []
        self.__thread = None

    def __del__(self):
        "finalizer"
        self.close()

    def __str__(self):
        return "[DataReader]"

    def post_fork_parent(self):
        """post-fork parent setup."""
        os.close(self.write_fd)
        self.write_fd = None

    def post_fork_child(self):
        """post-fork child setup."""
        self.read_fh.close()
        
    def post_exec_parent(self):
        "called to do any post-exec handling in the parent"
        self.__thread = threading.Thread(target=self.__reader)
        self.__thread.start()
        
    def close(self):
        "close pipes and terminate thread"
        if self.__thread is not None:
            self.__thread.join()
            self.__thread = None
        if self.read_fh is not None:
            self.read_fh.close()
            self.read_fh = None
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None

    def __reader(self):
        "child read thread function"
        self.__buffer.append(self.read_fh.read())

    @property
    def data(self):
        "return buffered data as a string"
        return "".join(self.__buffer)

class DataWriter(Dev):
    """Object to asynchronously write data to process from memory via a pipe.  A
    thread is use to prevent deadlock when both reading and writing to a child
    pipeline.
    """

    def __init__(self, data):
        Dev.__init__(self)
        self.__data = data
        self.read_fd, write_fd = os.pipe()
        self.write_fh = os.fdopen(write_fd, "wb")
        self.__thread = None
        
    def __del__(self):
        "finalizer"
        self.close()

    def __str__(self):
        return "[DataWriter]"

    def post_fork_parent(self):
        """post-fork parent setup."""
        os.close(self.read_fd)
        self.read_fd = None

    def post_fork_child(self):
        """post-fork child setup."""
        self.write_fh.close()
        self.write_fh = None
        
    def post_exec_parent(self):
        "called to do any post-exec handling in the parent"
        self.__thread = threading.Thread(target=self.__writer)
        self.__thread.start()
        
    def close(self):
        "close pipes and terminate thread"
        if self.__thread is not None:
            self.__thread.join()
            self.__thread = None
        if self.read_fd is not None:
            os.close(self.read_fd)
            self.read_fd = None
        if self.write_fh is not None:
            self.write_fh.close()
            self.write_fh = None

    def __writer(self):
        "write thread function"
        try:
            self.write_fh.write(self.__data)
            self.write_fh.close()
            self.write_fh = None
        except IOError as ex:
            # don't raise error on broken pipe
            if ex.errno != errno.EPIPE:
                raise

class File(Dev):
    """A file path for input or output, used for specifying stdio associated
    with files."""

    def __init__(self, path, mode="r"):
        """constructor, mode is standard r,w, or a with optional, but meaningless, b"""
        Dev.__init__(self)
        self.__path = path
        self.__mode = mode
        # only one of the file descriptors is ever opened
        self.read_fd = self.write_fd = None
        # must follow setting *_fd fields for __del__
        _validate_mode(mode, allow_append=True)
        if self.__mode[0] == 'r':
            self.read_fd = os.open(self.__path, os.O_RDONLY)
        elif self.__mode[0] == 'w':
            self.write_fd = os.open(self.__path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o666)
        else:
            self.write_fd = os.open(self.__path, os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o666)

    def __del__(self):
        self.close()
    def __str__(self):
        return self.__path

    def close(self):
        if self.read_fd is not None:
            os.close(self.read_fd)
            self.read_fd = None
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None

    def post_fork_parent(self):
        """post-fork child setup."""
        self.close()

class _SiblingPipe(Dev):
    """Interprocess communication between two child process by anonymous
    pipes."""

    def __init__(self):
        Dev.__init__(self)
        self.read_fd, self.write_fd = os.pipe()

    def __del__(self):
        "finalizer"
        self.close()

    def __str__(self):
        return "[Pipe]"

    def post_exec_parent(self):
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
        self.read_fh = os.fdopen(read_fd, "rb")
        self.write_fh = os.fdopen(write_fd, "wb")
        try:
            self.__set_close_on_exec(self.write_fh)
        except:
            self.close()
            raise

    @staticmethod
    def __set_close_on_exec( fh):
        flags = fcntl.fcntl(fh.fileno(), fcntl.F_GETFD)
        fcntl.fcntl(fh.fileno(), fcntl.F_SETFD, flags|fcntl.FD_CLOEXEC)

    def __del__(self):
        self.close()
    
    def close(self):
        "close pipes if open"
        if self.read_fh != None:
            self.read_fh.close()
            self.read_fh = None
        if self.write_fh != None:
            self.write_fh.close()
            self.write_fh = None
        
    def post_fork_parent(self):
        "post fork handling in parent"
        self.write_fh.close()
        self.write_fh = None

    def post_fork_child(self):
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

