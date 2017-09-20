===============================
Pipettor Overview
===============================

pipettor - robust, easy to use Python package for running Unix process pipelines

Features
--------

* Creating process pipelines in Python is either complex (e.g. ``subprocess``),
  or not robust (e.g. ``os.system()``).  This package provides aims to address
  these shortcomings.
* Command pipelines are simply specified as a sequence of commands, with each
  command represented as a sequence of arguments.
* Failure of any process in the pipeline results in an exception, with ``stderr``
  included in the exception.
* Pipeline ``stdin/stdout/stderr`` can be passed through from parent process,
  redirected to a file, or read/written by the parent process.
* Asynchronous reading and writing to and from the pipeline maybe done without risk of
  deadlock.
* Pipeline can run asynchronously or block until completion.
* File-like objects for reading or writing a pipeline.
* Documentation: https://pipettor.readthedocs.org.

