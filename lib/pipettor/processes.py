# Copyright 2006-2015 Mark Diekhans
"""
Robust, easy to use Unix process pipelines.
"""
import os
import signal
import shlex
import logging
import subprocess
import enum
from io import UnsupportedOperation
from threading import RLock
from pipettor.devices import Dev
from pipettor.devices import DataReader
from pipettor.devices import _SiblingPipe
from pipettor.devices import File
from pipettor.exceptions import PipettorException
from pipettor.exceptions import ProcessException
from pipettor.exceptions import _warn_error_during_error_handling

# FIXME: C-c problems:
# http://code.activestate.com/recipes/496735-workaround-for-missed-sigint-in-multithreaded-prog/
# http://bugs.python.org/issue21822
# FIXME above handled by subprocess??

_defaultLogger = None
_defaultLogLevel = logging.DEBUG

def setDefaultLogger(logger):
    """Set the default pipettor logger used in logging command and errors.
    If None, there is no default logging.  The logger can be the name of
    a logger or the logger itself.  Standard value is None"""
    global _defaultLogger
    _defaultLogger = logging.getLogger(logger) if isinstance(logger, str) else logger

def getDefaultLogger():
    """return the current value of the pipettor default logger"""
    return _defaultLogger

def setDefaultLogLevel(level):
    """Set the default pipettor log level to use in logging command and errors.
    Standard value is logging.DEBUG"""
    global _defaultLogLevel
    _defaultLogLevel = level

def getDefaultLogLevel():
    """Get the default pipettor log level to use in logging command and errors."""
    return _defaultLogLevel

def setDefaultLogging(logger, level):
    """Set both default logger and level. Either can be None to leave as default"""
    if logger is not None:
        setDefaultLogger(logger)
    if level is not None:
        setDefaultLogLevel(level)

def _getLoggerToUse(logger):
    """if logger is None, get default, otherwise if it's a string, look it up,
    otherwise it's the logger object."""
    if logger is None:
        return _defaultLogger
    elif isinstance(logger, str):
        return logging.getLogger(logger)
    else:
        return logger

def _getLogLevelToUse(logLevel):
    "get log level to use, either what is specified or default"
    return logLevel if logLevel is not None else getDefaultLogLevel()

class State(enum.IntEnum):
    """Current state of a process"""
    PREINIT = 0
    STARTUP = 1
    RUNNING = 2
    FINISHED = 4

class Process(object):
    """A process, represented as a node a pipeline, connected by Dev objects.

    Process arguments can be can be any object, with str() being called on
    the object before exec.

    If the stdin/out/err arguments can have the following values:
       - None - stdio file descriptior is inherited.
       - str - opened as a file
       - int -  file number
       - file-like object - fileno() is dupped
       - a Dev derived object

    If stderr is an instance of DataReader, then stderr is included in
    ProcessException on process error.  If the class DataReader is passed
    in as stderr, a DataReader object is created.

    start() must be called to run process
    """

    def __init__(self, cmd, stdin=None, stdout=None, stderr=None):
        self.lock = RLock()
        self.cmd = tuple(cmd)
        # stdio and argument Dev association
        self.stdin = self._stdio_assoc(stdin, "r")
        self.stdout = self._stdio_assoc(stdout, "w")
        if stderr == DataReader:
            stderr = DataReader(errors='backslashreplace')
        self.stderr = self._stdio_assoc(stderr, "w")
        self.popen = None
        self.pid = None
        self.pgid = None
        self.returncode = None  # exit code, or -signal
        # FIXME: should this just be exception for the users??
        self.procExcept = None  # exception because of failed process
        self.state = State.PREINIT
        self.forced = False    # force termination during error cleanup

    def __str__(self):
        "get simple description of process"
        return " ".join([shlex.quote(str(arg)) for arg in self.cmd])

    def _stdio_assoc(self, spec, mode):
        """pre-fork check a stdio spec validity and associate Dev or file
        number.  mode is mode in child"""
        if (spec is None) or isinstance(spec, int):
            return spec  # passed unchanged
        elif isinstance(spec, Dev):
            spec._bind_to_process(self, mode)
            return spec  # passed unchanged
        elif callable(getattr(spec, "fileno", None)):
            return spec.fileno()  # is file-like
        elif isinstance(spec, str):
            return File(spec, mode)
        else:
            raise PipettorException("invalid stdio specification object type: {} {}".format(type(spec), spec))

    def _get_child_stdio(self, spec, stdfd):
        """get fd to pass to child as one of the stdio handles."""
        if spec is None:
            return stdfd
        elif isinstance(spec, int):
            return spec
        elif isinstance(spec, Dev):
            return spec.read_fd if stdfd == 0 else spec.write_fd
        else:
            # this should have been detected earlier
            raise PipettorException("_get_child_stdio logic error: {} {}".format(type(spec), stdfd))

    def _start_process(self, pgid):
        """Do work of starting the process.  If pgid is None, this process
        becomes group leader, otherwise this process is added to group pgid."""
        self.state = State.STARTUP    # do first to prevent restarts on error

        # standard dance to get process group set
        # preexec_fn will go away: https://bugs.python.org/issue38435
        if pgid is None:
            preexecFn = lambda: os.setpgid(os.getpid(), os.getpid())  # noqa
        else:
            preexecFn = lambda: os.setpgid(os.getpid(), pgid)  # noqa

        try:
            self.popen = subprocess.Popen(self.cmd,
                                          stdin=self._get_child_stdio(self.stdin, 0),
                                          stdout=self._get_child_stdio(self.stdout, 1),
                                          stderr=self._get_child_stdio(self.stderr, 2),
                                          preexec_fn=preexecFn)
        except Exception as ex:
            raise ProcessException(str(self)) from ex
        self.pid = self.popen.pid
        self.pgid = self.pid if pgid is None else pgid
        self.state = State.RUNNING

    def _start(self, pgid):
        """Start the process,  If pgid is None, this process
        becomes group leader."""
        try:
            self._start_process(pgid)
        except BaseException as ex:
            self.procExcept = ex
        if self.procExcept is not None:
            raise self.procExcept

    @property
    def running(self):
        "determined if this process has been running"
        return self.state is State.RUNNING

    @property
    def finished(self):
        "determined if been detected as finished (waited on)"
        return self.state is State.FINISHED

    def _parent_stdio_exit_close(self):
        "close devices on edit"
        # MUST do before reading stderr in _handle_error_exit
        for std in (self.stdin, self.stdout, self.stderr):
            if isinstance(std, Dev):
                std.close()

    def _handle_error_exit(self):
        # get saved stderr, if possible
        stderr = None
        if isinstance(self.stderr, DataReader):
            stderr = self.stderr.data
        # don't save exception if we force it to be killed
        if not self.forced:
            self.procExcept = ProcessException(str(self), self.returncode, stderr)

    def _handle_exit(self, waitStat):
        """Handle process exiting, saving status  """
        self.state = State.FINISHED
        assert os.WIFEXITED(waitStat) or os.WIFSIGNALED(waitStat)
        self.returncode = os.WEXITSTATUS(waitStat) if os.WIFEXITED(waitStat) else -os.WTERMSIG(waitStat)
        # must tell subprocess.Popen about this
        self.popen.returncode = self.returncode
        self._parent_stdio_exit_close()  # MUST DO BEFORE _handle_error_exit
        if not ((self.returncode == 0) or (self.returncode == -signal.SIGPIPE)):
            self._handle_error_exit()

    def _waitpid(self, flag=0):
        "Do waitpid and handle exit if finished, return True if finished"
        if self.pid is None:
            raise PipettorException("process has not been started")
        w = os.waitpid(self.pid, flag)
        if w[0] != 0:
            self._handle_exit(w[1])
        return (w[0] != 0)

    def poll(self):
        """Check if the process has completed.  Return True if it
        has, False if it hasn't."""
        with self.lock:
            if self.state is State.FINISHED:
                return True
            return self._waitpid(os.WNOHANG)

    def _force_finish(self):
        """Force termination of process.  The forced flag is set, as an
        indication that this was not a primary failure in the pipeline.
        """
        with self.lock:
            # check if finished before killing
            if (self.state is State.RUNNING) and (not self.poll()):
                self.forced = True
                os.kill(self.pid, signal.SIGKILL)
                self._waitpid()

    def failed(self):
        "check if process failed, call after poll() or wait()"
        return self.procExcept is not None


class Pipeline(object):
    """
    A process pipeline.  Once constructed, the pipeline
    is started with start(), poll(), or wait() functions.

    The cmds argument is either a list of arguments for a single process, or a
    list of such lists for a pipeline. If the stdin/out/err arguments are
    none, the open files are are inherited.  Otherwise they can be string file
    names, file-like objects, file number, or Dev object.  Stdin is input to
    the first process, stdout is output to the last process and stderr is
    attached to all processed. DataReader and DataWriter objects can be
    specified for stdin/out/err asynchronously I/O with the pipeline without
    the danger of deadlock.

    If stderr is the class DataReader, a new instance is created for each
    process in the pipeline. The contents of stderr will include an
    exception if an occurs in that process.  If an instance of DataReader
    is provided, the contents of stderr from all process will be included in
    the exception.

    Command arguments will be converted to strings.

    The logger argument can be the name of a logger or a logger object.  If
    none, default is user.
    """
    def __init__(self, cmds, *, stdin=None, stdout=None, stderr=DataReader,
                 logger=None, logLevel=None):
        self.lock = RLock()
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.procs = []
        self.devs = set()
        self.pgid = None       # process group leader
        self.bypid = dict()    # indexed by pid
        self.state = State.PREINIT
        self.logger = _getLoggerToUse(logger)
        self.logLevel = _getLogLevelToUse(logLevel)

        if isinstance(cmds[0], str):
            cmds = [cmds]  # one-process pipeline
        cmds = self._stringify(cmds)
        try:
            self._setup_processes(cmds)
        except BaseException:
            self._error_cleanup()
            raise

    @staticmethod
    def _stringify(cmds):
        ncmds = []
        for cmd in cmds:
            ncmds.append([str(a) for a in cmd])
        return ncmds

    @property
    def running(self):
        "determined if this process has been running"
        return self.state is State.RUNNING

    @property
    def finished(self):
        "determined if been detected as finished (waited on)"
        return self.state is State.FINISHED

    def _log(self, level, message, ex=None):
        """If logging is available and enabled, log message and optional
        exception"""
        if (self.logger is not None) and (self.logger.isEnabledFor(level)):
            kwargs = {}
            if ex is not None:
                kwargs["exc_info"] = ex
            self.logger.log(level, "{}: {}".format(message, str(self)), **kwargs)

    def _setup_processes(self, cmds):
        prevPipe = None
        lastCmdIdx = len(cmds) - 1
        for i in range(len(cmds)):
            prevPipe = self._add_process(cmds[i], prevPipe, (i == lastCmdIdx), self.stdin, self.stdout, self.stderr)

    def _add_process(self, cmd, prevPipe, isLastCmd, stdinFirst, stdoutLast, stderr):
        """add one process to the pipeline, return the output pipe if not the last process"""
        if prevPipe is None:
            stdin = stdinFirst  # first process in pipeline
        else:
            stdin = prevPipe
        if isLastCmd:
            outPipe = None
            stdout = stdoutLast  # last process in pipeline
        else:
            outPipe = stdout = _SiblingPipe()
        try:
            self._create_process(cmd, stdin, stdout, stderr)
        except BaseException:
            if outPipe is not None:
                outPipe.close()
            raise
        return outPipe

    def _create_process(self, cmd, stdin, stdout, stderr):
        """create process and track Dev objects"""
        proc = Process(cmd, stdin, stdout, stderr)
        self.procs.append(proc)
        # Proc maybe have wrapped a Dev
        for std in (proc.stdin, proc.stdout, proc.stderr):
            if isinstance(std, Dev):
                self.devs.add(std)

    def __str__(self):
        """get a string describing the pipe"""
        desc = str(self.procs[0])
        if self.stdin not in (None, 0):
            desc += " <" + str(self.stdin)
        if len(self.procs) > 1:
            desc += " | " + " | ".join([str(proc) for proc in self.procs[1:]])
        if self.stdout not in (None, 1):
            desc += " >" + str(self.stdout)
        if self.stderr == DataReader:
            desc += " 2>[DataReader]"  # instance made in Process
        elif self.stderr not in (None, 2):
            desc += " 2>" + str(self.stderr)
        return desc

    def _start_process(self, proc):
        proc._start(self.pgid)
        self.bypid[proc.pid] = proc
        self.pgid = proc.pgid

    def _start_processes(self):
        for proc in self.procs:
            self._start_process(proc)

    def _post_start_parent(self):
        for d in self.devs:
            d._post_start_parent()

    def _finish(self):
        "finish up when no errors have occurred"
        assert not self.failed()
        self.state = State.FINISHED
        for d in self.devs:
            d.close()
        self._log(self.logLevel, "success")

    def _log_failure(self, ex):
        self._log(logging.ERROR, "failure", ex)

    def _error_cleanup_dev(self, dev):
        try:
            dev.close()
        except Exception as ex:
            _warn_error_during_error_handling("error during device cleanup on error", ex)

    def _error_cleanup_process(self, proc):
        try:
            if not proc.finished:
                proc._force_finish()
        except Exception as ex:
            _warn_error_during_error_handling("error during process cleanup on error", ex)

    def _error_cleanup(self):
        """forced cleanup of child processed after failure"""
        self.state = State.FINISHED
        for d in self.devs:
            self._error_cleanup_dev(d)
        for p in self.procs:
            self._error_cleanup_process(p)

    def _start_guts(self):
        self._log(self.logLevel, "start")
        self.state = State.RUNNING
        # clean up devices and process if there is a failure
        try:
            self._start_processes()
            self._post_start_parent()
        except Exception as ex:
            self._log_failure(ex)
            self._error_cleanup()
            raise

    def start(self):
        """start processes"""
        if self.state >= State.STARTUP:
            raise PipettorException("Pipeline is already been started")
        with self.lock:
            self._start_guts()

    def _raise_if_failed(self):
        """raise exception if any process has one, otherwise do nothing"""
        try:
            for p in self.procs:
                if p.procExcept is not None:
                    raise p.procExcept
        except Exception as ex:
            self._log_failure(ex)
            raise ex

    def _poll_guts(self):
        for p in self.procs:
            if not p.poll():
                return False
        self._finish()
        return True

    def poll(self):
        """Check if all of the processes have completed.  Return True if it
        has, False if it hasn't."""
        with self.lock:
            if self.state is State.PREINIT:
                self.start()
            try:
                return self._poll_guts()
            except BaseException:
                self._error_cleanup()
                raise

    def _wait_on_one(self, proc):
        "wait on the next process in group to complete"
        w = os.waitpid(proc.pid, 0)
        self.bypid[w[0]]._handle_exit(w[1])

    def _wait_guts(self):
        if self.state < State.RUNNING:
            self.start()
        try:
            for p in self.procs:
                if not p.finished:
                    self._wait_on_one(p)
        except BaseException as ex:
            self._log_failure(ex)
            self._error_cleanup()
            raise ex
        self._raise_if_failed()

    def wait(self):
        """Wait for all of the process to complete. Generate an exception if
        any exits non-zero or signals. Starts process if not already
        running."""
        with self.lock:
            self._wait_guts()
            self._finish()

    def _shutdown(self):
        "guts of shutdown"
        self.kill(sig=signal.SIGKILL)
        try:
            self.wait()
        except PipettorException:
            pass  # ignore errors we report

    def shutdown(self):
        """Close down the pipeline prematurely. If the pipeline is running,
        it's killed.  This does not report errors from child process and
        differs from wait in the fact that it doesn't start the pipeline if it
        has not been started, just frees up open pipes. Primary intended
        for error recovery"""
        with self.lock:
            if self.logger is not None:
                self.logger.log(self.logLevel, "Shutting down pipeline: {}".format(str(self)))
            if self.state is State.RUNNING:
                self._shutdown()
            elif self.state is not State.FINISHED:
                self._finish()  # just clean up pipes

    def failed(self):
        "check if any process failed, call after poll() or wait()"
        with self.lock:
            for p in self.procs:
                if p.failed():
                    return True
            return False

    def kill(self, sig=signal.SIGTERM):
        "send a signal to all of the processes in the pipeline"
        for p in self.procs:
            os.kill(p.pid, sig)


class Popen(Pipeline):
    """File-like object of processes to read from or write to a Pipeline.

    The cmds argument is either a list of arguments for a single process,
    or a list of such lists for a pipeline.  Mode is 'r' for a pipeline
    who's output will be read, or 'w' for a pipeline to that is to have
    data written to it.  If stdin or stdout is specified, and is a string,
    it is a file to open as other file at the other end of the pipeline.
    If it's not a string, it is assumed to be a file object to use for
    input or output.  For a read pipe, only stdin can be specified, for a
    write pipe, only stdout can be used.

    read pipeline ('r'):
      stdin --> cmd[0] --> ... --> cmd[n] --> Popen

    write pipeline ('w')
      Popen --> cmd[0] --> ... --> cmd[n] --> stdout

    Command arguments will be converted to strings.

    The logger argument can be the name of a logger or a logger object.  If
    none, default is user.

    Specifying binary access results in data of type bytes, otherwise str type
    is returned.  The buffering, encoding, and errors arguments are as used in
    the open() function.
    """

    # note: this follows I/O _pyio.py structure, but doesn't extend class
    # due to it doing both binary and text I/O.  Probably could do this
    # with some kind of dynamic base class setting.

    def __init__(self, cmds, mode='r', *, stdin=None, stdout=None, logger=None, logLevel=None,
                 buffering=-1, encoding=None, errors=None):
        self.mode = mode
        self._pipeline_fh = None
        self._child_fd = None
        if mode.find('a') >= 0:
            raise PipettorException("can not specify append mode")
        if mode.find('r') >= 0:
            if stdout is not None:
                raise PipettorException("can not specify stdout with read mode")
        else:
            if stdin is not None:
                raise PipettorException("can not specify stdin with write mode")

        pipe_read_fd, pipe_write_fd = os.pipe()
        if mode.find('r') >= 0:
            firstIn = stdin
            lastOut = pipe_write_fd
            self._child_fd = pipe_write_fd
            self._pipeline_fh = open(pipe_read_fd, mode, buffering=buffering, encoding=encoding, errors=errors)
        else:
            firstIn = pipe_read_fd
            lastOut = stdout
            self._child_fd = pipe_read_fd
            self._pipeline_fh = open(pipe_write_fd, mode, buffering=buffering, encoding=encoding, errors=errors)
        super(Popen, self).__init__(cmds, stdin=firstIn, stdout=lastOut, logger=logger, logLevel=logLevel)
        self.start()
        os.close(self._child_fd)
        self._child_fd = None

    ### Internal ###

    def _close(self):
        if self._pipeline_fh is not None:
            self._pipeline_fh.close()
            self._pipeline_fh = None
        if self._child_fd is not None:
            os.close(self._child_fd)
            self._child_fd = None

    def _unsupported(self, name):
        """from _pyio.py: raise an OSError exception for unsupported operations."""
        raise UnsupportedOperation("%s.%s() not supported" %
                                   (self.__class__.__name__, name))

    def _checkClosed(self, msg=None):
        """Internal: raise a ValueError if file is closed
        """
        if self.closed:
            raise ValueError("I/O operation on closed file."
                             if msg is None else msg)

    ### Positioning ###

    def seek(self, pos, whence=0):
        """Changing stream position not supported"""
        self._unsupported("seek")

    def tell(self):
        """Return an int indicating the current stream position."""
        return self._pipeline_fh.tell()

    def truncate(self, pos=None):
        """Truncate file unsupported"""
        self._unsupported("truncate")

    ### Flush and close ###

    def flush(self):
        "Flush the internal I/O buffer."
        self._pipeline_fh.flush()

    def close(self):
        "wait for process to complete, with an error if it exited non-zero"
        with self.lock:
            self._close()
            if self.state is not State.FINISHED:
                self.wait()

    def __del__(self):
        """Destructor.  Calls close()."""
        if self._pipeline_fh is not None:
            self.close()

    ### Inquiries ###

    def seekable(self):
        """Not seekable"""
        return False

    def readable(self):
        """Return a bool indicating whether object was opened for reading."""
        return self._pipeline_fh.readable()

    def writable(self):
        """Return a bool indicating whether object was opened for writing."""
        return self._pipeline_fh.writable()

    @property
    def closed(self):
        """closed: bool.  True if the file has been closed."""
        if self._pipeline_fh is None:
            return True
        else:
            return self._pipeline_fh.closed

    ### Context manager ###

    def __enter__(self):
        "support for with statement"
        self._checkClosed()
        return self

    def __exit__(self, type, value, traceback):
        "support for with statement"
        self.close()

    ### Lower-level APIs ###

    def fileno(self):
        "get the integer OS-dependent file handle"
        return self._pipeline_fh.fileno()

    def isatty(self):
        """Return a bool indicating whether this is an 'interactive' stream.
        """
        self._checkClosed()
        return False

    ### read, write and readline[s] and writelines ###

    def read(self, size=-1):
        return self._pipeline_fh.read(size)

    def readline(self, size=-1):
        return self._pipeline_fh.readline(size)

    def readlines(self, size=-1):
        return self._pipeline_fh.readlines(size)

    def __iter__(self):
        "iter over contents of file"
        return self._pipeline_fh.__iter__()

    def __next__(self):
        return next(self._pipeline_fh)

    def write(self, str):
        "Write string str to file."
        self._pipeline_fh.write(str)

    def writelines(self, lines):
        """Write a list of lines to the stream.

        Line separators are not added, so it is usual for each of the lines
        provided to have a line separator at the end.
        """
        self._pipeline_fh.writelines(lines)

    ### not part of file-like ###

    def wait(self):
        """wait to for processes to complete, generate an exception if one
        exits no-zero"""
        with self.lock:
            self._close()
            super(Popen, self).wait()

    def poll(self):
        "poll is not allowed for Pipeline objects"
        # FIXME: don't know what to do about our open pipe keeping process from
        # exiting so we can get a status, so disallow it. Not sure how to
        # address this.  Can probably address this with select on pipe.
        self._unsupported("poll")
