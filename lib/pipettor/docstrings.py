"""
Common documentation strings used functions and methods to avoid
repeating the same text
"""

_doc_cmds = """\
    :param cmds: A list (or tuple) of arguments for a single process, or a
        list of such lists for a pipeline. Arguments are converted to strings."""
_doc_stdin = """\
    :param stdin: Input to the first process. Can be None (inherit), a
         filename, file-like object, file descriptor, a :class:`pipettor.File`
         object, or a :class:`pipettor.DataWriter` object.
"""
_doc_stdout = """\
    :param stdout: Output from the last process. Can be None (inherit), a
         filename, file-like object, file descriptor, a :class:`pipettor.File`
         object, or a :class:`pipettor.DataReader` object."""
_doc_stdout = """\
    :param stderr: stderr for the pipeline.  Can be None (inherit), a
         filename, file-like object, file descriptor, a :class:`pipettor.File`
         object, or a :class:`pipettor.DataReader` object.  It may also be the
         class :class:`pipettor.DataReader` itself, in which case a DataReader
         will be create for each process encoding errors handled using
        ``backslashreplace``."""
_doc_stdout = """\
    :param logger: Name of the logger or a `Logger` instance to use instead of the default.
    :param logLevel: Log level to use instead of the default."""

_doc_raises = """\
    :raises pipettor.ProcessException: if the pipeline fails."""
