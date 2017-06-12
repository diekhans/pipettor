"""
Robust, easy to use Unix process pipelines.
"""
from __future__ import print_function
import shlex
from pipettor.exceptions import PipettorException, ProcessException
from pipettor.devices import Dev, DataReader, DataWriter, File
from pipettor.processes import Pipeline, Popen, setDefaultLogger, getDefaultLogger, setDefaultLogLevel, getDefaultLogLevel, setDefaultLogging, _isstr

__version__ = "0.1.2"


def run(cmds, stdin=None, stdout=None, stderr=DataReader, logger=None, logLevel=None):
    """Construct and run an process pipeline. If any of the processes fail,
    a ProcessException is throw.

    `cmds` is either a list of arguments for a single process, or a list of
    such lists for a pipeline. If the `stdin`, `stdout`, or `stderr` arguments
    are none, the open files are are inherited.  Otherwise they can be string
    file names, file-like objects, file number, or :class:`pipettor.Dev``
    object.  `stdin` is input to the first process, `stdout` is output to the
    last process and `stderr` is attached to all processed.
    :class:`pipettor.DataReader` and :class:`pipettor.DataWriter`
    objects can be specified for `stdin`, `stdout`, or `stderr` asynchronously
    I/O with the pipeline without the danger of deadlock.

    If stderr is the class DataReader, a new instance is created for each
    process in the pipeline. The contents of stderr will include an exception
    if an occurs in that process.  If an instance of
    :class:`pipettor.DataReader` is provided, the contents of stderr from all
    process will be included in the exception.

    The logger argument can be the name of a logger or a logger object.  If
    none, default is user.
    """
    Pipeline(cmds, stdin=stdin, stdout=stdout, stderr=stderr, logger=logger, logLevel=logLevel).wait()


def runout(cmds, stdin=None, stderr=DataReader, logger=None, logLevel=None):
    """
    Construct and run an process pipeline, returning the output. If any of the
    processes fail, a ProcessException is throw.

    See the :func:`pipettor.run` function for more details.  Use
    `str.splitlines()` to split result into lines.

    The logger argument can be the name of a logger or a logger object.  If
    none, default is user.
    """
    dr = DataReader()
    Pipeline(cmds, stdin=stdin, stdout=dr, stderr=stderr, logger=logger, logLevel=logLevel).wait()
    return dr.data


def _lexcmds(cmds):
    """spit pipeline specification into arguments"""
    if _isstr(cmds):
        return shlex.split(cmds)
    else:
        return [shlex.split(cmd) if _isstr(cmd) else cmd for cmd in cmds]


def runlex(cmds, stdin=None, stdout=None, stderr=DataReader, logger=None, logLevel=None):
    """
    Call :func:`pipettor.run`, first splitting commands specified
    as strings are split into arguments using `shlex.split`.

    If `cmds` is a string, it is split into arguments and run as
    as a single process.  If `cmds` is a list, a multi-process
    pipeline is created.  Elements that are strings are split
    into arguments to form commands.  Elements that are lists
    are treated as commands without splitting.

    The logger argument can be the name of a logger or a logger object.  If
    none, default is user.
    """
    run(_lexcmds(cmds), stdin=stdin, stdout=stdout, stderr=stderr, logger=logger, logLevel=logLevel)


def runlexout(cmds, stdin=None, stderr=DataReader, logger=None, logLevel=None):
    """
    Call :func:`pipettor.runout`, first splitting commands specified
    as strings are split into arguments using `shlex.split`.

    If `cmds` is a string, it is split into arguments and run as
    as a single process.  If `cmds` is a list, a multi-process
    pipeline is created.  Elements that are strings are split
    into arguments to form commands.  Elements that are lists
    are treated as commands without splitting.

    The logger argument can be the name of a logger or a logger object.  If
    none, default is user.
    """
    return runout(_lexcmds(cmds), stdin=stdin, stderr=stderr, logger=logger, logLevel=logLevel)


__all__ = (PipettorException.__name__, ProcessException.__name__,
           Dev.__name__, DataReader.__name__, DataWriter.__name__,
           File.__name__, Pipeline.__name__, Popen.__name__,
           setDefaultLogger.__name__, getDefaultLogger.__name__,
           setDefaultLogLevel.__name__, getDefaultLogLevel.__name__,
           setDefaultLogging.__name__,
           run.__name__, runout.__name__, runlex.__name__, runlexout.__name__)
