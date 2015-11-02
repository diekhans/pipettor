# Copyright 2015 Mark Diekhans
import sys
import traceback
import signal

def _signal_num_to_name(num):
    "get name for a signal number"
    # find name in signal namespace
    for key in vars(signal):
        if (getattr(signal, key) == num) and key.startswith("SIG") and (key.find("_") < 0):
            return key
    return "signal"+str(num)

class PipettorException(Exception):
    """Base class for exceptions.  This implements exception chaining and
    stores a stack trace.

    To chain an exception
       try:
          ...
       except Exception as ex:
          raise PipettorException("more stuff", ex)
    """
    def __init__(self, msg, cause=None):
        """Constructor."""
        if (cause is not None) and (not isinstance(cause, PipettorException)):
            # store stack trace in other Exception types
            exi = sys.exc_info()
            if exi is not None:
                setattr(cause, "stackTrace", traceback.format_list(traceback.extract_tb(exi[2])))
        Exception.__init__(self, msg)
        self.msg = msg
        self.cause = cause
        self.stackTrace = traceback.format_list(traceback.extract_stack())[0:-1]

    def __str__(self):
        "recursively construct message for chained exception"
        desc = self.msg
        if self.cause is not None:
            desc += ",\n    caused by: " + self.cause.__class__.__name__ + ": " +  str(self.cause)
        return desc

    def format(self):
        "Recursively format chained exceptions into a string with stack trace"
        return PipettorException.formatExcept(self)

    @staticmethod
    def formatExcept(ex, doneStacks=None):
        """Format any type of exception, handling PipettorException objects and
        stackTrace added to standard Exceptions."""
        desc = type(ex).__name__ + ": "
        # don't recurse on PipettorExceptions, as they will include cause in message
        if isinstance(ex, PipettorException):
            desc += ex.msg + "\n"
        else:
            desc +=  str(ex) +  "\n"
        st = getattr(ex, "stackTrace", None)
        if st is not None:
            if doneStacks is None:
                doneStacks = set()
            for s in st:
                if s not in doneStacks:
                    desc += s
                    doneStacks.add(s)
        ca = getattr(ex, "cause", None)
        if ca is not None:
            desc += "caused by: " + PipettorException.formatExcept(ca, doneStacks)
        return desc

class ProcessException(PipettorException):
    """Exception associated with running a process.  A None returncode indicates
    a exec failure."""
    def __init__(self, procDesc, returncode=None, stderr=None, cause=None):
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
        PipettorException.__init__(self, msg, cause=cause)

