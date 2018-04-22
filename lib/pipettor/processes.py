# Copyright 2006-2015 Mark Diekhans
"""
Robust, easy to use Unix process pipelines.
"""
from __future__ import print_function
import six
import os
import sys
import signal
import gc
import errno
import pipes
import logging
from threading import RLock
from pipettor.devices import _open_compat
from pipettor.devices import Dev
from pipettor.devices import DataReader
from pipettor.devices import _SiblingPipe
from pipettor.devices import File
from pipettor.devices import _StatusPipe
from pipettor.exceptions import PipettorException
from pipettor.exceptions import ProcessException
from pipettor.exceptions import _warn_error_during_error_handling

xrange = six.moves.builtins.range

# FIXME: C-c problems:
# http://code.activestate.com/recipes/496735-workaround-for-missed-sigint-in-multithreaded-prog/
# http://bugs.python.org/issue21822

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except ValueError:
    MAXFD = 256


class _SetpgidCompleteMsg(object):
    "message sent to by first process to indicate that setpgid is complete"
    pass


_defaultLogger = None
_defaultLogLevel = logging.DEBUG


def setDefaultLogger(logger):
    """Set the default pipettor logger used in logging command and errors.
    If None, there is no default logging.  The logger can be the name of
    a logger or the logger itself.  Standard value is None"""
    global _defaultLogger
    _defaultLogger = logging.getLogger(logger) if isinstance(logger, six.string_types) else logger


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
    elif isinstance(logger, six.string_types):
        return logging.getLogger(logger)
    else:
        return logger


def _getLogLevelToUse(logLevel):
    "get log level to use, either what is specified or default"
    return logLevel if logLevel is not None else getDefaultLogLevel()


class Process(object):
    """A process, represented as a node a pipeline Proc objects, connected by
    Dev objects.

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
            stderr = DataReader()
        self.stderr = self._stdio_assoc(stderr, "w")
        self.pid = None
        self.pgid = None
        self.status_pipe = None
        self.returncode = None  # exit code, or -signal
        # FIXME: should this just be exception for the users??
        self.exceptinfo = None  # (exception, value, traceback)
        self.started = False
        self.finished = False
        self.forced = False    # force termination during error cleanup

    def __str__(self):
        "get simple description of process"
        return " ".join([pipes.quote(str(arg)) for arg in self.cmd])

    def _wrapProcessException(self, cause):
        """wrap in ProcessException without losing causing exception, on Py3, use
        exception chaining, on PY2, set as stderr, however __cause__ is not
        pickled, so we set it in stderr now too.
        """
        if six.PY3:
            try:
                # FIXME: __cause__ not pickled, so set stderr too
                six.raise_from(ProcessException(str(self), stderr=repr(cause)), cause)
            except Exception as ex2:
                return ex2
        else:
            return ProcessException(str(self), stderr=repr(cause))

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
        elif isinstance(spec, six.string_types):
            return File(spec, mode)
        else:
            raise PipettorException("invalid stdio specification object type: {} {}".format(type(spec), spec))

    def _child_stdio_setup(self, spec, stdfd):
        """post-fork setup one of the stdio fds."""
        fd = None
        if spec is None:
            fd = stdfd
        elif isinstance(spec, int):
            fd = spec
        elif isinstance(spec, Dev):
            fd = spec.read_fd if stdfd == 0 else spec.write_fd
        if fd is None:
            # this should have been detected before forking
            raise PipettorException("_child_stdio_setup logic error: {} {}".format(type(spec), stdfd))
        # dup to target descriptor if not already there
        if fd != stdfd:
            os.dup2(fd, stdfd)
            # Don't close source file here, must delay closing in case stdout/err is same fd.
            # Close is done by _child_close_files

    def _child_close_files(self):
        "clone non-stdio files"
        keepOpen = set([self.status_pipe.write_fh.fileno()])
        for fd in xrange(3, MAXFD + 1):
            try:
                if fd not in keepOpen:
                    os.close(fd)
            except OSError:
                pass

    def _child_set_signals(self):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # ensure terminate on pipe close

    def _child_setup_devices(self):
        "post-fork setup of devices"
        for std in (self.stdin, self.stdout, self.stderr):
            if isinstance(std, Dev):
                std._post_fork_child()

    def _child_setup_process_group(self):
        """setup process group, if this is the first process, it becomes the
        process group leader and sends a message when it's done"""
        if self.pgid is None:
            self.pgid = os.getpid()
            os.setpgid(self.pid, self.pgid)
            self.status_pipe.send(_SetpgidCompleteMsg())
        else:
            os.setpgid(self.pid, self.pgid)

    def _child_exec(self):
        "guts of start child process"
        self.status_pipe._post_fork_child()
        self._child_setup_process_group()
        self._child_setup_devices()
        self._child_stdio_setup(self.stdin, 0)
        self._child_stdio_setup(self.stdout, 1)
        self._child_stdio_setup(self.stderr, 2)
        self._child_close_files()
        self._child_set_signals()
        os.execvp(self.cmd[0], self.cmd)

    def _child_do_exec(self):
        " in child process"
        try:
            self._child_exec()
        except Exception as ex:
            if not isinstance(ex, ProcessException):
                ex = self._wrapProcessException(ex)
            self.status_pipe.send(ex)
            os._exit(255)

    def _child_start(self):
        "start in child process"
        try:
            self._child_do_exec()
        except Exception as ex:
            _warn_error_during_error_handling("child process exec error handling logic error", ex)
        finally:
            os.abort()  # should never make it here

    def _parent_setup_process_group_leader(self):
        status = self.status_pipe.receive()
        if status is None:
            raise PipettorException("child process exited without setting process group")
        elif isinstance(status, _SetpgidCompleteMsg):
            self.pgid = self.pid
        elif isinstance(status, Exception):
            raise status
        else:
            raise PipettorException("expected _SetpgidCompleteMsg message, got {}".format(status))

    def _parent_start(self):
        "start in parent process"
        self.status_pipe._post_fork_parent()
        if self.pgid is None:
            # first process is process leader.
            self._parent_setup_process_group_leader()

    def _start_processes(self, pgid):
        "Do work of starting the process, if pgid is None do group leader setup"
        self.pgid = pgid
        self.status_pipe = _StatusPipe()
        self.started = True  # do first to prevent restarts on error

        # From subprocess.py: Disable gc to avoid bug where gc -> file_dealloc ->
        # write to stderr -> hang.  http://bugs.python.org/issue1336
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            self.pid = os.fork()
        finally:
            if gc_was_enabled:
                gc.enable()
        if self.pid == 0:
            self._child_start()
        else:
            self._parent_start()

    def _start(self, pgid):
        "start the process,, if pgid is do group leader setup"
        try:
            self._start_processes(pgid)
        except BaseException:
            self.exceptinfo = sys.exc_info()
        if self.exceptinfo is not None:
            self._raise_if_failed()

    def _execwait(self):
        """wait on exec to happen, receive status from child raising the
        exception if one was send"""
        ex = self.status_pipe.receive()
        if ex is not None:
            if not isinstance(ex, Exception):
                ex = PipettorException("unexpected object return from child exec status pipe: {}: {}".format(type(ex), ex))
            if not isinstance(ex, ProcessException):
                ex = self._wrapProcessException(ex)
            raise ex
        self.status_pipe.close()

    def running(self):
        "determined if this process has been started, but not finished"
        with self.lock:
            return self.started and not self.finished

    def _raise_if_failed(self):
        """raise exception if one is saved, otherwise do nothing"""
        if self.exceptinfo is not None:
            six.reraise(self.exceptinfo[0], self.exceptinfo[1], self.exceptinfo[2])

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
        # don't save exception if we force it to be ill
        if not self.forced:
            self.exceptinfo = (ProcessException, ProcessException(str(self), self.returncode, stderr), None)

    def _handle_exit(self, waitStat):
        """Handle process exiting, saving status  """
        self.finished = True
        assert(os.WIFEXITED(waitStat) or os.WIFSIGNALED(waitStat))
        self.returncode = os.WEXITSTATUS(waitStat) if os.WIFEXITED(waitStat) else -os.WTERMSIG(waitStat)
        self._parent_stdio_exit_close()  # MUST DO BEFORE _handle_error_exit
        if not ((self.returncode == 0) or (self.returncode == -signal.SIGPIPE)):
            self._handle_error_exit()
        self.status_pipe.close()

    def _waitpid(self, flag=0):
        "Do waitpid and handle exit if finished, return True if finished"
        w = os.waitpid(self.pid, flag)
        if w[0] != 0:
            self._handle_exit(w[1])
        return (w[0] != 0)

    def poll(self):
        """Check if the process has completed.  Return True if it
        has, False if it hasn't."""
        with self.lock:
            if self.finished:
                return True
            return self._waitpid(os.WNOHANG)

    def _force_finish(self):
        """Force termination of process.  The forced flag is set, as an
        indication that this was not a primary failure in the pipeline.
        """
        with self.lock:
            # check if finished before killing
            if self.started and not self.poll():
                self.forced = True
                os.kill(self.pid, signal.SIGKILL)
                self._waitpid()

    def failed(self):
        "check if process failed, call after poll() or wait()"
        return self.exceptinfo is not None


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
    def __init__(self, cmds, stdin=None, stdout=None, stderr=DataReader,
                 logger=None, logLevel=None):
        self.lock = RLock()
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.procs = []
        self.devs = set()
        self.pgid = None       # process group leader
        self.bypid = dict()    # indexed by pid
        self.started = False   # have processes been started
        self.running = False   # processes are running (or wait has not been called)
        self.finished = False  # have all processes finished
        self.logger = _getLoggerToUse(logger)
        self.logLevel = _getLogLevelToUse(logLevel)

        if isinstance(cmds[0], six.string_types):
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

    @staticmethod
    def _getLogKwargs(ex):
        kwargs = {}
        if ex is not None:
            if six.PY2:
                # need to just get some stack trace for 2.7
                kwargs["exc_info"] = (type(ex), ex, sys.exc_info()[2])
            else:
                kwargs["exc_info"] = ex
        return kwargs

    def _log(self, level, message, ex=None):
        """If logging is available and enabled, log message and optional
        exception"""
        if (self.logger is not None) and (self.logger.isEnabledFor(level)):
            self.logger.log(level, "{}: {}".format(message, str(self)), **self._getLogKwargs(ex))

    def _setup_processes(self, cmds):
        prevPipe = None
        lastCmdIdx = len(cmds) - 1
        for i in xrange(len(cmds)):
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
        if self.pgid is None:
            self.pgid = proc.pgid
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

    def _post_fork_parent(self):
        for d in self.devs:
            d._post_fork_parent()

    def _start_process(self, proc):
        proc._start(self.pgid)
        self.bypid[proc.pid] = proc
        assert(proc.pgid is not None)
        if self.pgid is None:
            self.pgid = proc.pgid

    def _start_processes(self):
        for proc in self.procs:
            self._start_process(proc)

    def _exec_barrier(self):
        for p in self.procs:
            p._execwait()

    def _post_exec_parent(self):
        for d in self.devs:
            d._post_exec_parent()

    def _finish(self):
        "finish up when no errors have occurred"
        assert not self.failed()
        self.finished = True
        self.running = False
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
            proc._force_finish()
        except Exception as ex:
            _warn_error_during_error_handling("error during process cleanup on error", ex)

    def _error_cleanup(self):
        """forced cleanup of child processed after failure"""
        self.finished = True
        self.running = False
        for d in self.devs:
            self._error_cleanup_dev(d)
        for p in self.procs:
            self._error_cleanup_process(p)

    def _start_guts(self):
        self._log(self.logLevel, "start")
        self.started = True
        self.running = True
        # clean up devices and process if there is a failure
        try:
            self._start_processes()
            self._post_fork_parent()
            self._exec_barrier()
            self._post_exec_parent()
        except Exception as ex:
            self._log_failure(ex)
            self._error_cleanup()
            raise

    def start(self):
        """start processes"""
        if self.started:
            raise PipettorException("Pipeline is already been started")
        with self.lock:
            self._start_guts()

    def _raise_if_failed(self):
        """raise exception if any process has one, otherwise do nothing"""
        try:
            for p in self.procs:
                p._raise_if_failed()
        except Exception as ex:
            self._log_failure(ex)
            raise

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
            if not self.started:
                self.start()
            try:
                return self._poll_guts()
            except BaseException:
                self._error_cleanup()
                raise

    def _wait_on_one(self):
        "wait on the next process in group to complete, return False if no more"
        try:
            w = os.waitpid(-self.pgid, 0)
        except OSError as ex:
            if ex.errno == errno.ECHILD:
                return False
            raise
        self.bypid[w[0]]._handle_exit(w[1])
        return True

    def _wait_guts(self):
        if not self.started:
            self.start()
        try:
            while self._wait_on_one():
                pass
        except Exception as ex:
            self._log_failure(ex)
            self._error_cleanup()
            raise
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
            if self.running:
                self._shutdown()
            elif not self.finished:
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
        os.kill(-self.pgid, sig)


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

    For Python3, specifying binary access results in data of type bytes,
    otherwise str.  The buffering, encoding, and errors arguments are as used
    in the Python 3 open() function.  With Python 2, encoding and error is
    ignored.
    """

    def __init__(self, cmds, mode='r', stdin=None, stdout=None, logger=None, logLevel=None,
                 buffering=-1, encoding=None, errors=None):
        self.mode = mode
        self._parent_fh = None
        self._child_fd = None
        if mode.find('a') >= 0:
            raise PipettorException("can not specify stdout with read mode")
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
            self._parent_fh = _open_compat(pipe_read_fd, mode, buffering=buffering, encoding=encoding, errors=errors)
        else:
            firstIn = pipe_read_fd
            lastOut = stdout
            self._child_fd = pipe_read_fd
            self._parent_fh = _open_compat(pipe_write_fd, mode, buffering=buffering, encoding=encoding, errors=errors)
        super(Popen, self).__init__(cmds, stdin=firstIn, stdout=lastOut, logger=logger, logLevel=logLevel)
        self.start()
        os.close(self._child_fd)
        self._child_fd = None

    def _close(self):
        if self._parent_fh is not None:
            self._parent_fh.close()
            self._parent_fh = None
        if self._child_fd is not None:
            os.close(self._child_fd)
            self._child_fd = None

    def __enter__(self):
        "support for with statement"
        return self

    def __exit__(self, type, value, traceback):
        "support for with statement"
        self.close()

    def __iter__(self):
        "iter over contents of file"
        return self._parent_fh.__iter__()

    def next(self):
        return self._parent_fh.next()

    def flush(self):
        "Flush the internal I/O buffer."
        self._parent_fh.flush()

    def fileno(self):
        "get the integer OS-dependent file handle"
        return self._parent_fh.fileno()

    def write(self, str):
        "Write string str to file."
        self._parent_fh.write(str)

    def read(self, size=-1):
        return self._parent_fh.read(size)

    def readline(self, size=-1):
        return self._parent_fh.readline(size)

    def readlines(self, size=-1):
        return self._parent_fh.readlines(size)

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
        raise PipettorException("Pipeline.poll() is not supported")

    def close(self):
        "wait for process to complete, with an error if it exited non-zero"
        with self.lock:
            self._close()
            if not self.finished:
                self.wait()
