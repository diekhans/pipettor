"""
Robust, easy to use Unix process pipelines.
"""
import shlex
from pipettor.docstrings import doc_cmd_std_args, doc_open_other_args, doc_raises, doc_error_handling
from pipettor.exceptions import PipettorException, ProcessException
from pipettor.devices import DataReader, DataWriter, File
from pipettor.processes import LOGGER_NAME  # noqa
from pipettor.processes import Pipeline, Popen, setDefaultLogger, getDefaultLogger, setDefaultLogLevel, getDefaultLogLevel, setDefaultLogging

__version__ = "1.2.0"

def run(cmds, stdin=None, stdout=None, stderr=DataReader, logger=None, logLevel=None):
    """
    Construct and run a process pipeline.
    """    # doc extended below after class creation
    Pipeline(cmds, stdin=stdin, stdout=stdout, stderr=stderr, logger=logger, logLevel=logLevel).wait()


# extend documentation from common text
run.__doc__ += '\n' + doc_cmd_std_args

def runout(cmds, stdin=None, stderr=DataReader, binary=False, logger=None, logLevel=None,
           buffering=-1, encoding=None, errors=None, newline=None):
    """
    Construct and run a process pipeline, returning the output.

    """    # doc extended below after class creation
    dr = DataReader(binary=binary, buffering=buffering,
                    encoding=encoding, errors=errors, newline=newline)
    Pipeline(cmds, stdin=stdin, stdout=dr, stderr=stderr,
             logger=logger, logLevel=logLevel).wait()
    return dr.data


# extend documentation from common text
runout.__doc__ += '\n' + doc_cmd_std_args + doc_open_other_args + doc_raises + """

Use ``str.splitlines()`` to split the result into lines.

""" + doc_error_handling

def _lexcmds(cmds):
    """spit pipeline specification into arguments"""
    if isinstance(cmds, str):
        return shlex.split(cmds)
    else:
        return [shlex.split(cmd) if isinstance(cmd, str) else cmd
                for cmd in cmds]


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
