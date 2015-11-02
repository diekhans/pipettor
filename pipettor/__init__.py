"""
Robust, easy to use Unix process pipelines.
"""
__version__ = "0.1a"

from pipettor.exceptions import PipettorException, ProcessException
from pipettor.devices import Dev, DataReader, DataWriter,  File
from pipettor.processes import Pipeline,  Popen
