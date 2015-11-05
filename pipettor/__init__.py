"""
Robust, easy to use Unix process pipelines.
"""
__version__ = "0.1a"

from pipettor.exceptions import PipettorException, ProcessException
from pipettor.devices import Dev, DataReader, DataWriter,  File
from pipettor.processes import Pipeline,  Popen

__all__ = (PipettorException.__name__, ProcessException.__name__,
           Dev.__name__, DataReader.__name__, DataWriter.__name__,
           File.__name__, Pipeline.__name__, Popen.__name__,)
