============
Design notes
============



It would simplify the implementation if this could be build on top of the
`subprocess` module or `_posixsubprocess`.  However these do not allow for
setting the process group. 

=============
Design issues
=============

* issues with signals and process groups
  - creating a process group for the pipeline allows waiting on any process to complete, so polling isn't necessary
  - however, this prevents signs from being directly propagated
  - don't use process groups
* python's handling of SIGINT is especially problematic (see subprocess.py workarounds),
  as it delays signal delivery.

