============
Design notes
============

Pipettor now builds on top of `subprocess`. However, it uses the soon to be
depreciated `preexec_fn` to set the process group id.  A request has been
add a function to set pgid has been added to the depreciation ticket.

=============
Design issues
=============

* issues with signals and process groups
  - creating a process group for the pipeline allows waiting on any process to complete, so polling isn't necessary
  - however, this prevents signals from being directly propagated
  - don't use process groups
* python's handling of SIGINT is especially problematic, as it delays signal delivery.
  Switch to using `subprocess` should improve the behavior.

