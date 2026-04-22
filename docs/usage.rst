.. usage

=====
Usage
=====

A single process in pipettor is specified as sequence (list or tuple) of
the command and its arguments.  A process pipeline is specified as a sequence
of such commands (lists of lists, lists of tuples, etc).
Functions to create processes check if a specified command is a sequence of
commands or a single command based on the sequence structure.

Example commands are::

   ("date",)
   ("sort", "-u", "/etc/stuff")
   [("sort", "-u", "/etc/stuff"), ("wc", "-l")]

Commands are *not* run through the UNIX shell to prevent security and
robustness problems.

A non-zero exit or signal termination from any process in a pipe results in a
:class:`pipettor.ProcessException`, which contains the `stderr` of the
failed process unless redirected.

The simplest way to execute a pipeline synchronously is to use
the :func:`pipettor.run` or :func:`pipettor.runout` functions::

    import pipettor
    pipettor.run([("sort", "-u", "/etc/hosts"), ("wc", "-l")], stdout="hosts.linecnt")
    out = pipettor.runout([("sort", "-u", "/etc/hosts"), ("wc", "-l")])

    
File-like objects to or from a pipeline maybe create using the
:class:`pipettor.Popen` class::

    import pipettor
    rfh = pipettor.Popen([("sort", "-u", "/etc/hosts"), ("wc", "-l")])
    wfh = pipettor.Popen([("sort", "-u"), ("wc", "-l")], "w", stdout="uniq.linecnt")

Bidirectional (interleaved read/write) pipelines are created with
mode ``'r+'`` (or ``'w+'``, or ``'rb+'`` for binary).  Neither
``stdin`` nor ``stdout`` may be given; both are connected to the
``Popen`` object and accessed with the usual file-like methods.
I/O is asynchronous, so writes and reads can be freely interleaved
without risk of deadlock.  When finished writing, call
:meth:`pipettor.Popen.close_stdin` so the child sees EOF::

    import pipettor
    with pipettor.Popen([("cat", "-u"), ("cat", "-u")], "r+") as pl:
        responses = []
        for i in range(20):
            pl.write(f"request {i}\n")
            responses.append(pl.readline())
        pl.close_stdin()
        tail = pl.read()          # drain any remaining output

In-memory buffering is unbounded by default; pass ``max_queue=N`` to
cap the items buffered per direction when one side may vastly outrun
the other.

For mixed binary/text on the two sides, build a :class:`pipettor.Pipeline`
directly with :class:`pipettor.StreamReader` and
:class:`pipettor.StreamWriter` instances, which accept independent
``binary``, ``buffering``, ``encoding``, ``errors``, ``newline``, and
``max_queue`` arguments.
         
In-memory data can be also be written to pipelines using :class:`pipettor.DataWriter` objects::

    import pipettor
    dw = pipettor.DataWriter("line3\nline1\nline2\nline1\n")
    pipettor.run([("sort", "-u",), ("wc", "-l")], stdin=dw, stdout="writer.linecnt")


Data can be read from pipelines into memory using :class:`pipettor.DataReader` objects::

    import pipettor
    dr = pipettor.DataReader()
    pipettor.run([("sort", "-u", "/etc/hosts"), ("wc", "-l")], stdout=dr)
    print(dr.data)

The :func:`pipettor.runlex` or :func:`pipettor.runlexout` functions pass string arguments
through `shlex.split` to split them into arguments::

    import pipettor
    out = pipettor.runlexout("sort -u /etc/hosts")
    out = pipettor.runlexout(["sort -u /etc/hosts", ("wc", "-l")])

Full control of process pipelines can be achieved using :class:`pipettor.Pipeline`
class directly.  The :class:`pipettor.DataReader` and :class:`pipettor.DataWriter`
classes (in-memory accumulator / source) and the
:class:`pipettor.StreamReader` and :class:`pipettor.StreamWriter` classes
(file-like read/write) all do their I/O asynchronously, so reading and writing
to the same pipeline is safe from deadlock.
