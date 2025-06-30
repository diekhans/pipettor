"""
Common documentation strings used functions and methods to avoid
repeating the same text
"""

# to work with Sphinx after concatenation, strings must not start with a
# newline and must end with a newline.

doc_cmd_std_args = """\
:param cmds: A list (or tuple) of arguments for a single process, or a
    list of such lists for a pipeline. Arguments are converted to strings.
:param stdin: Input to the first process. Can be None (inherit),
    filename, file-like object, file descriptor, a :class:`pipettor.File`
    object, or a :class:`pipettor.DataWriter` object.
:param stdout: Output from the last process. Can be None (inherit), a
    filename, file-like object, file descriptor, a :class:`pipettor.File`
    object, or a :class:`pipettor.DataReader` object.
:param stderr: stderr for the pipeline. Can be None (inherit), a
    filename, file-like object, file descriptor, a :class:`pipettor.File`
    object, or a :class:`pipettor.DataReader` object. It may also be the
    class :class:`pipettor.DataReader` itself.  See discussion below.
:param logger: Name of the logger or a `Logger` instance. If ``None``,
    the default ``pipettor`` logger is used.
:param logLevel: Log level to use instead of the default.
"""

doc_raises = """\
:raises pipettor.ProcessException: if the a process in pipeline exits
    with a non-zero status
"""

doc_error_handling = """\
They specification of ``stderr`` controls how errors are reported.  If a
:class:`pipettor.DataReader` class is provided for ``stderr``, a
``DataReader`` object will be created from it for each process to collect
that processes stderr output.  If the pipeline fails, the contents of
stderr from the first process that failed will be included in the
:class:`pipettor.ProcessException` object. If an instance of
:class:`pipettor.DataReader` is provided, stderr from all processes is
combined and that is returned in the failure.  It is recommended that a
DataReader object be created with ``errors="backslashreplace"`` to prevent
invalid UTF-8 characters from generating confusing errors.
"""

doc_open_mode_arg = """\
:param mode: specifies the mode in which the file is opened. It defaults to 'r'.
    See open() for more details.
"""

doc_open_other_args = """\
:param buffering: controls buffering.
    See open() for more details.
:param encoding:  name of the encoding used to decode or encode the file
    See open() for more details.
:param errors: how encoding errors are handled.
    See open() for more details.
:param newline: controls how universal newlines works
    See open() for more details.
"""
