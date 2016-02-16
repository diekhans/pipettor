.. usage

=====
Usage
=====

A single processes in pipettor are specified as sequence (list or tuple) of
the command and its arguments.  A process pipeline is specified as a sequence
of such commands.  Functions to create processes check if a specified
command is a sequence of commands or a single command based on the sequence
structure.

Examples commands are::

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
    pipettor.run([("sort", "-u", "/etc/stuff"), ("wc", "-l")], stdout="stuff.linecnt")
    out = pipettor.runout([("sort", "-u", "/etc/stuff"), ("wc", "-l")])

    
File line objects to or from a file maybe create using the
:class:`pipettor.Popen` class::

    import pipettor
    rfh = pipettor.Popen([("sort", "-u", "/etc/stuff"), ("wc", "-l")])
    wfh = pipettor.Popen([("sort", "-u"), ("wc", "-l")], "w", stdout="uniq.linecnt")
         
