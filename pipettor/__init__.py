"""
Robust, easy to use Unix process pipelines.
"""
from __future__ import print_function
from pipettor.exceptions import PipettorException, ProcessException
from pipettor.devices import Dev, DataReader, DataWriter, File
from pipettor.processes import Pipeline, Popen

__version__ = "0.1a1"


def run(cmds, stdin=None, stdout=None, stderr=DataReader):
    """
    Construct and run an process pipeline. If any of the processes fail,
    a ProcessException is throw.

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
    Pipeline(cmds, stdin=stdin, stdout=stdout, stderr=stderr).wait()


def runout(cmds, stdin=None, stderr=DataReader):
    """
    Construct and run an process pipeline, returning the output. If any of the
    processes fail, a ProcessException is throw.

    See the call() function for more details.
    """
    dr = DataReader()
    Pipeline(cmds, stdin=stdin, stdout=dr, stderr=stderr).wait()
    return dr.data


__all__ = (PipettorException.__name__, ProcessException.__name__,
           Dev.__name__, DataReader.__name__, DataWriter.__name__,
           File.__name__, Pipeline.__name__, Popen.__name__,
           run.__name__, runout.__name__,)
