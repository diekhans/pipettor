# Copyright 2006-2016 Mark Diekhans
from __future__ import print_function
import sys
import traceback
import signal
from warnings import warn


def _signal_num_to_name(num):
    "get name for a signal number"
    # find name in signal namespace
    for key in vars(signal):
        if (getattr(signal, key) == num) and key.startswith("SIG") and (key.find("_") < 0):
            return key
    return "signal" + str(num)


class PipettorException(Exception):
    """Base class for Pipettor exceptions."""
    pass


class ProcessException(PipettorException):
    """Exception associated with running a process.  A None returncode indicates
    a exec failure."""
    def __init__(self, procDesc, returncode=None, stderr=None):
        self.procDesc = procDesc
        self.returncode = returncode
        self.stderr = stderr
        if returncode is None:
            msg = "exec failed"
        elif (returncode < 0):
            msg = "process signaled: " + _signal_num_to_name(-returncode)
        else:
            msg = "process exited " + str(returncode)
        if procDesc is not None:
            msg += ": " + procDesc
        if (stderr is not None) and (len(stderr) != 0):
            msg += ":\n" + stderr
        super(ProcessException, self).__init__(msg)

    def __reduce__(self):
        # __reduce__ is used, otherwise we had problems with the msg having
        # duplicated string
        return (ProcessException, (self.procDesc, self.returncode, self.stderr))


class ErrorDuringErrorHandlingWarning(Warning):
    """An error occurred while handing another error"""
    pass


def _warn_error_during_error_handling(msg, exception):
    "called to issue warning on error during error handling"
    exi = sys.exc_info()
    stack = "" if exi is None else "".join(traceback.format_list(traceback.extract_tb(exi[2]))) + "\n"
    warn(msg + " " + str(exception) + "\n" + stack, ErrorDuringErrorHandlingWarning)
