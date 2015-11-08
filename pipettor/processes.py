# Copyright 2006-2015 Mark Diekhans
"""
Robust, easy to use Unix process pipelines.
"""
from __future__ import print_function
import os
import sys
import signal
import errno
import traceback
import pipes
from pipettor.devices import _validate_mode
from pipettor.devices import Dev
from pipettor.devices import DataReader
from pipettor.devices import _SiblingPipe
from pipettor.devices import File
from pipettor.devices import _StatusPipe
from pipettor.exceptions import PipettorException
from pipettor.exceptions import ProcessException


# Why better that subprocess:
#   - natural pipeline
#   - stderr thrown as excpetion

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256


class _SetpgidCompleteMsg(object):
    "message sent to by first process to indicate that setpgid is complete"
    pass


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
        self.cmd = tuple(cmd)
        # stdio and argument Dev association
        self.stdin = self.__stdio_assoc(stdin, "r")
        self.stdout = self.__stdio_assoc(stdout, "w")
        if stderr == DataReader:
            stderr = DataReader()
        self.stderr = self.__stdio_assoc(stderr, "w")
        self.pid = None
        self.pgid = None
        self.status_pipe = None
        self.returncode = None  # exit code, or -signal
        self.exceptinfo = None  # (exception, value, traceback)
        self.started = False
        self.finished = False
        self.forced = False    # force termination during error cleanup

    def __str__(self):
        "get simple description of process"
        strs = []
        for arg in self.cmd:
            strs.append(pipes.quote(str(arg)))
        return " ".join(strs)

    def __stdio_assoc(self, spec, mode):
        """pre-fork check a stdio spec validity and associate Dev or file
        number.  mode is mode in child"""
        if (spec is None) or isinstance(spec, int) or isinstance(spec, Dev):
            return spec  # passed unchanged
        elif callable(getattr(spec, "fileno", None)):
            return spec.fileno()  # is file-like
        elif isinstance(spec, str) or isinstance(spec, unicode):
            return File(spec, mode)
        else:
            raise PipettorException("invalid stdio specification object type: " + str(type(spec)) + " " + str(spec))

    def __stdio_child_setup(self, spec, stdfd):
        """post-fork setup one of the stdio fds."""
        fd = None
        if spec is None:
            fd = stdfd
        elif isinstance(spec, int):
            fd = spec
        elif isinstance(spec, Dev):
            if stdfd == 0:   # stdin?
                fd = spec.read_fd
            else:
                fd = spec.write_fd
        if fd is None:
            # this should have been detected before forking
            raise PipettorException("__stdio_child_setup logic error: %s %s" % (str(type(spec)), stdfd))
        # dup to target descriptor if not already there
        if fd != stdfd:
            os.dup2(fd, stdfd)
            # Don't close source file here, must delay closing in case stdout/err is same fd.
            # Close is done by __close_files

    def __close_files(self):
        "clone non-stdio files"
        keepOpen = set([self.status_pipe.write_fh.fileno()])
        for fd in xrange(3, MAXFD+1):
            try:
                if fd not in keepOpen:
                    os.close(fd)
            except:
                pass

    def __child_setup_devices(self):
        "post-fork setup of devices"
        for std in (self.stdin, self.stdout, self.stderr):
            if isinstance(std, Dev):
                std._post_fork_child()

    def __child_setup_process_group(self):
        """setup process group, if this is the first process, it becomes the
        process group leader and sends a message when it's done"""
        if self.pgid is None:
            self.pgid = os.getpid()
            os.setpgid(self.pid, self.pgid)
            self.status_pipe.send(_SetpgidCompleteMsg())
        else:
            os.setpgid(self.pid, self.pgid)

    def __child_exec(self):
        "guts of start child process"
        self.status_pipe._post_fork_child()
        self.__child_setup_process_group()
        self.__child_setup_devices()
        self.__stdio_child_setup(self.stdin, 0)
        self.__stdio_child_setup(self.stdout, 1)
        self.__stdio_child_setup(self.stderr, 2)
        self.__close_files()
        # FIXME: might want to reset other signals
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # ensure terminate on pipe close
        os.execvp(self.cmd[0], self.cmd)

    def __child_do_exec(self):
        " in child process"
        try:
            self.__child_exec()
        except Exception as ex:
            # FIXME: use isinstance(ex, ProcessException) causes error in python
            # FIXME: lets see if it is fixed
            if not isinstance(ex, ProcessException):
                ex = ProcessException(str(self), cause=ex)
            self.status_pipe.send(ex)
            os._exit(255)

    def __child_start(self):
        "start in child process"
        try:
            self.__child_do_exec()
        except Exception as ex:
            # FIXME: make something
            sys.stderr.write("child process exec error handling logic error: " + str(ex)+"\n")
        finally:
            os.abort()  # should never make it here

    def __parent_setup_process_group_leader(self):
        status = self.status_pipe.receive()
        if status is None:
            raise PipettorException("child process exited without setting process group")
        elif isinstance(status, _SetpgidCompleteMsg):
            self.pgid = self.pid
        elif isinstance(status, Exception):
            raise status
        else:
            raise PipettorException("expected _SetpgidCompleteMsg message, got " + str(status))

    def __parent_start(self):
        "start in parent process"
        self.status_pipe._post_fork_parent()
        if self.pgid is None:
            # first process is process leader.
            self.__parent_setup_process_group_leader()

    def __start_processes(self, pgid):
        "Do work of starting the process, if pgid is None do group leader setup"
        self.pgid = pgid
        self.status_pipe = _StatusPipe()
        self.started = True  # do first to prevent restarts on error
        self.pid = os.fork()
        if self.pid == 0:
            self.__child_start()
        else:
            self.__parent_start()

    def _start(self, pgid):
        "start the process,, if pgid is do group leader setup"
        try:
            self.__start_processes(pgid)
        except:
            self.exceptinfo = sys.exc_info()
        if self.exceptinfo is not None:
            self._raise_if_failed()

    def _execwait(self):
        """wait on exec to happen, receive status from child raising the
        exception if one was send"""
        ex = self.status_pipe.receive()
        if ex is not None:
            if not isinstance(ex, Exception):
                ex = PipettorException("unexpected object return from child exec status pipe: %s: %s" % (str(type(ex)), str(ex)))
            if not isinstance(ex, ProcessException):
                ex = ProcessException(str(self), cause=ex)
            raise ex
        self.status_pipe.close()

    def running(self):
        "determined if this process has been started, but not finished"
        return self.started and not self.finished

    def _raise_if_failed(self):
        """raise exception if one is saved, otherwise do nothing"""
        if self.exceptinfo is not None:
            raise self.exceptinfo[0], self.exceptinfo[1], self.exceptinfo[2]

    def __handle_error_exit(self):
        # get saved stderr, if possible
        stderr = None
        if isinstance(self.stderr, DataReader):
            stderr = self.stderr.data
        # don't save exception if we force it to be ill
        if not self.forced:
            self.exceptinfo = (ProcessException(str(self), self.returncode, stderr), None, None)

    def _handle_exit(self, waitStat):
        """Handle process exiting, saving status  """
        self.finished = True
        assert(os.WIFEXITED(waitStat) or os.WIFSIGNALED(waitStat))
        self.returncode = os.WEXITSTATUS(waitStat) if os.WIFEXITED(waitStat) else -os.WTERMSIG(waitStat)
        if not ((self.returncode == 0) or (self.returncode == -signal.SIGPIPE)):
            self.__handle_error_exit()
        self.status_pipe.close()

    def poll(self):
        """Check if the process has completed.  Return True if it
        has, False if it hasn't."""
        if self.finished:
            return True
        w = os.waitpid(self.pid, os.WNOHANG)
        if w[0] != 0:
            self._handle_exit(w[1])
        return (w[0] != 0)

    def _force_finish(self):
        """Force termination of process.  The forced flag is set, as an
        indication that this was not a primary failure in the pipeline.
        """
        if self.started and not self.finished:
            # check if finished before killing
            if not self.poll():
                self.forced = True
                os.kill(self.pid, signal.SIGKILL)
                w = os.waitpid(self.pid, 0)
                self._handle_exit(w[1])

    def failed(self):
        "check if process failed, call after poll() or wait()"
        return (self.exceptInfo is not None)


class Pipeline(object):
    """
    A process pipeline.  Once constructed, the pipeline
    is started with start(), poll(), or wait() functions.

    Cmds is either a list of arguments for a single process, or a list of such
    lists for a pipeline. If the stdin/out/err arguments are none, the
    open files are are inherited.  Otherwise they can be string file
    names, file-like objects, file number, or Dev object.  Stdin is input
    to the first process, stdout is output to the last process and stderr
    is attached to all processed. DataReader and DataWriter objects can be
    specified for stdin/out/err asynchronously I/O with the pipeline
    without the danger of deadlock.

    If stderr is the class DataReader, a new instance is created for each
    process in the pipeline. The contents of stderr will include an
    exception if an occurs in that process.  If an instance of DataReader
    is provided, the contents of stderr from all process will be included in
    the exception.
    """
    def __init__(self, cmds, stdin=None, stdout=None, stderr=None):
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

        if isinstance(cmds[0], str):
            cmds = [cmds]  # one-process pipeline
        try:
            self.__setup_processes(cmds)
        except:
            self.__error_cleanup()
            raise

    def __setup_processes(self, cmds):
        prevPipe = None
        lastCmdIdx = len(cmds)-1
        for i in xrange(len(cmds)):
            prevPipe = self.__add_process(cmds[i], prevPipe, (i == lastCmdIdx), self.stdin, self.stdout, self.stderr)

    def __add_process(self, cmd, prevPipe, isLastCmd, stdinFirst, stdoutLast, stderr):
        """add one process to the pipeline, return the output pipe if not the last process"""
        if prevPipe is None:
            stdin = stdinFirst  # first process in pipeline
        else:
            stdin = prevPipe
        if isLastCmd:
            outPipe = None
            stdout = stdoutLast  # last process in pipeline
        else:
            outPipe = _SiblingPipe()
            stdout = outPipe
        try:
            self.__create_process(cmd, stdin, stdout, stderr)
        except:
            if outPipe is not None:
                outPipe.close()
            raise
        return outPipe

    def __create_process(self, cmd, stdin, stdout, stderr):
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
            desc += " <"+str(self.stdin)
        if len(self.procs) > 1:
            desc += " | " + " | ".join([str(proc) for proc in self.procs[1:]])
        if self.stdout not in (None, 1):
            desc += " >"+str(self.stdout)
        if self.stderr not in (None, 2):
            desc += " 2>"+str(self.stderr)
        return desc

    def __post_fork_parent(self):
        for d in self.devs:
            d._post_fork_parent()

    def __start_process(self, proc):
        proc._start(self.pgid)
        self.bypid[proc.pid] = proc
        assert(proc.pgid is not None)
        if self.pgid is None:
            self.pgid = proc.pgid

    def __start(self):
        for proc in self.procs:
            self.__start_process(proc)

    def __exec_barrier(self):
        for p in self.procs:
            p._execwait()

    def __post_exec_parent(self):
        for d in self.devs:
            d._post_exec_parent()

    def __finish(self):
        "finish up when no errors have occurred"
        self.finished = True
        self.running = False
        for d in self.devs:
            d.close()

    def __error_cleanup_dev(self, dev):
        try:
            dev.close()
        except Exception as ex:
            # FIXME: use logging or warning
            exi = sys.exc_info()
            stack = "" if exi is None else "".join(traceback.format_list(traceback.extract_tb(exi[2])))+"\n"
            sys.stderr.write("pipettor dev cleanup exception: " + str(ex) + "\n" + stack)

    def __error_cleanup_process(self, proc):
        try:
            proc._force_finish()
        except Exception as ex:
            # FIXME: make optional
            sys.stderr.write("pipeline prococess cleanup exception: " + str(ex) + "\n")

    def __error_cleanup(self):
        """forced cleanup of child processed after failure"""
        self.finished = True
        self.running = False
        for d in self.devs:
            self.__error_cleanup_dev(d)
        for p in self.procs:
            self.__error_cleanup_process(p)

    def start(self):
        """start processes"""
        self.started = True
        self.running = True
        # clean up devices and process if there is a failure
        try:
            self.__start()
            # FIXME: really need both post fork and exec in parent
            self.__post_fork_parent()
            self.__exec_barrier()
            self.__post_exec_parent()
        except:
            self.__error_cleanup()
            raise

    def _raise_if_failed(self):
        """raise exception if any process has one, otherwise do nothing"""
        for p in self.procs:
            p._raise_if_failed()

    def __poll(self):
        for p in self.procs:
            if not p.poll():
                return False
        self.__finish()

    def poll(self):
        """Check if all of the processes have completed.  Return True if it
        has, False if it hasn't."""
        if not self.started:
            self.start()
        try:
            self.__poll()
        except:
            self.__error_cleanup()
            raise
        return True

    def __wait_on_one(self):
        "wait on the next process in group to complete, return False if no more"
        try:
            w = os.waitpid(-self.pgid, 0)
        except OSError as ex:
            if ex.errno == errno.ECHILD:
                return False
            raise
        p = self.bypid[w[0]]
        p._handle_exit(w[1])
        return True

    def __wait(self):
        while self.__wait_on_one():
            pass
        self.__finish()

    def wait(self):
        """Wait for all of the process to complete. Generate an exception if
        any exits non-zero or signals. Starts process if not already
        running."""
        if not self.started:
            self.start()
        try:
            self.__wait()
        except:
            self.__error_cleanup()
            raise
        self._raise_if_failed()

    def failed(self):
        "check if any process failed, call after poll() or wait()"
        for p in self.procs:
            if p.failed():
                return True
        return False

    def kill(self, sig=signal.SIGTERM):
        "send a signal to all of the processes in the pipeline"
        os.kill(-self.pgid, sig)


class Popen(Pipeline):
    """File-like object of processes to read from or write to a Pipeline.

    .. automethod:: __init__
    """

    def __init__(self, cmds, mode='r', other=None):
        """cmds is either a list of arguments for a single process, or a list of such
        lists for a pipeline.  Mode is 'r' for a pipeline who's output will be
        read, or 'w' for a pipeline to that is to have data written to it.  If
        other is specified, and is a string, it is a file to open as other
        file at the other end of the pipeline.  If it's not a string, it is
        assumed to be a file object to use for output.

        read pipeline ('r'):
          other --> cmd[0] --> ... --> cmd[n] --> Popen

        write pipeline ('w')
          Popen --> cmd[0] --> ... --> cmd[n] --> other

        """
        _validate_mode(mode, allow_append=False)
        self.mode = mode
        self.__parent_fh = None
        self.__child_fd = None

        pipe_read_fd, pipe_write_fd = os.pipe()
        if mode == "r":
            firstIn = other
            lastOut = pipe_write_fd
            self.__child_fd = pipe_write_fd
            self.__parent_fh = os.fdopen(pipe_read_fd, mode)
        else:
            firstIn = pipe_read_fd
            lastOut = other
            self.__child_fd = pipe_read_fd
            self.__parent_fh = os.fdopen(pipe_write_fd, mode)
        Pipeline.__init__(self, cmds, stdin=firstIn, stdout=lastOut)
        self.start()
        os.close(self.__child_fd)
        self.__child_fd = None

    def __del__(self):
        self.__close()

    def __close(self):
        if self.__parent_fh is not None:
            self.__parent_fh.close()
            self.__parent_fh = None
        if self.__child_fd is not None:
            os.close(self.__child_fd)
            self.__child_fd = None

    def __enter__(self):
        "support for with statement"
        return self

    def __exit__(self, type, value, traceback):
        "support for with statement"
        self.close()

    def __iter__(self):
        "iter over contents of file"
        return self.__parent_fh.__iter__()

    def next(self):
        return self.__parent_fh.next()

    def flush(self):
        "Flush the internal I/O buffer."
        self.__parent_fh.flush()

    def fileno(self):
        "get the integer OS-dependent file handle"
        return self.__parent_fh.fileno()

    def write(self, str):
        "Write string str to file."
        self.__parent_fh.write(str)

    def read(self, size=-1):
        return self.__parent_fh.read(size)

    def readline(self, size=-1):
        return self.__parent_fh.readline(size)

    def readlines(self, size=-1):
        return self.__parent_fh.readlines(size)

    def wait(self):
        """wait to for processes to complete, generate an exception if one
        exits no-zero"""
        Pipeline.wait(self)
        self.__close()

    def poll(self):
        "poll is not allowed for Pipeline objects"
        # don't know what to do about our open pipe, so disallow it
        raise PipettorException("Pipeline.poll() is not supported")

    def close(self):
        "wait for process to complete, with an error if it exited non-zero"
        self.__close()
        if not self.finished:
            self.wait()
