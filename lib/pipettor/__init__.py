"""
Robust, easy to use Unix process pipelines.
"""
import shlex
from pipettor.exceptions import PipettorException, ProcessException
from pipettor.devices import DataReader, DataWriter, File
from pipettor.processes import Pipeline, Popen, setDefaultLogger, getDefaultLogger, setDefaultLogLevel, getDefaultLogLevel, setDefaultLogging

__version__ = "1.1.0"


def run(cmds, stdin=None, stdout=None, stderr=DataReader, logger=None, logLevel=None):
    """
    Construct and run a process pipeline. If any of the processes fail,
    a :class:`pipettor.ProcessException` is raised.

    :param cmds: A list (or tuple) of arguments for a single process, or a
        list of such lists for a pipeline. Arguments are converted to strings.
    :param stdin: Input to the first process. Can be None (inherit), a
        filename, file-like object, file descriptor, a :class:`pipettor.File`
        object, or a :class:`pipettor.DataWriter`.
    :param stdout: Output from the last process. Same options as `stdin`, or a :class:`pipettor.DataReader`.
    :param stderr: stderr for all processes. Same options as `stdout`, or the
       :class:`pipettor.DataReader` class itself. In the latter case, a new
       instance is created with encoding errors handled using ``backslashreplace``.
    :param logger: Name of the logger or a `Logger` instance to use instead of the default.
    :param logLevel: Log level to use instead of the default.

    :raises pipettor.ProcessException: If the pipeline fails.

    If a :class:`pipettor.DataReader` is provided for `stderr` and the
    pipeline fails, the contents of stderr from all processes will be included
    in the :class:`pipettor.ProcessException` object.
    """
    Pipeline(cmds, stdin=stdin, stdout=stdout, stderr=stderr, logger=logger, logLevel=logLevel).wait()


def runout(cmds, stdin=None, stderr=DataReader, logger=None, logLevel=None,
           buffering=-1, encoding=None, errors=None, binary=False):
    """
    Construct and run a process pipeline, returning the output.
    If any of the processes fail, a :class:`pipettor.ProcessException` is raised.

    See the :func:`pipettor.run` function for more details. Use
    ``str.splitlines()`` to split the result into lines.

    :param buffering: Optional integer. If set to 0, unbuffered. 1 for line buffering. Any other positive integer for buffer size. Default is -1 (system default).
    :type buffering: int, optional
    :param encoding: Name of the encoding used to decode or encode the file. Only used in text mode. Defaults to None (system default).
    :type encoding: str, optional
    :param errors: Specifies how encoding/decoding errors are handled. Default is None (uses system default).
    :type errors: str, optional
    :param binary: If True, data is returned as `bytes`, otherwise as `str` using the specified encoding.
    :type binary: bool, optional

    :raises pipettor.ProcessException: If the pipeline fails.
    """
    dr = DataReader(binary=binary, buffering=buffering, encoding=encoding, errors=errors)
    Pipeline(cmds, stdin=stdin, stdout=dr, stderr=stderr,
             logger=logger, logLevel=logLevel).wait()
    return dr.data


def _lexcmds(cmds):
    """spit pipeline specification into arguments"""
    if isinstance(cmds, str):
        return shlex.split(cmds)
    else:
        return [shlex.split(cmd) if isinstance(cmd, str) else cmd for cmd in cmds]


def runlex(cmds, stdin=None, stdout=None, stderr=DataReader, logger=None, logLevel=None):
    """Call :func:`pipettor.run`, first splitting commands specified as strings
    are split into arguments using `shlex.split`.

    See :func:`run` for details.
    """
    run(_lexcmds(cmds), stdin=stdin, stdout=stdout, stderr=stderr, logger=logger, logLevel=None)


def runlexout(cmds, stdin=None, stderr=DataReader, logger=None, logLevel=None,
              buffering=-1, encoding=None, errors=None):
    """Call :func:`pipettor.runout`, first splitting commands specified
    as strings are split into arguments using `shlex.split`.

    See :func:`runout` for details.
    """
    return runout(_lexcmds(cmds), stdin=stdin, stderr=stderr, logger=logger, logLevel=logLevel,
                  buffering=buffering, encoding=encoding, errors=errors)


# n.b. all of the library API functions and classes need to be explicitly
# included in the docs/library.rst files
__all__ = (PipettorException.__name__, ProcessException.__name__,
           DataReader.__name__, DataWriter.__name__,
           File.__name__, Pipeline.__name__, Popen.__name__,
           setDefaultLogger.__name__, getDefaultLogger.__name__,
           setDefaultLogLevel.__name__, getDefaultLogLevel.__name__, setDefaultLogging.__name__,
           run.__name__, runout.__name__, runlex.__name__, runlexout.__name__)
