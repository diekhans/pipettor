.. :changelog:

History
=======

0.6.0 (2022-11-16)
-----------------
* remove use of deprecated pipes module


0.5.0 (2020-12-25)
-----------------
* Removed Python-2 support.
* Switch to using subprocess as a base rather interface directly
  with Unix system calls.  This lets subprocess deal with
  various issues dealing with the Python interpreter environment.  

0.4.0 (2018-04-21)
------------------
* Allow passing through universial newline mode for PY2.
* Fix bug with not using specified log level.


0.3.0 (2018-02-25)
-----------------------
* added open-stying buffering, encoding, and errors options
* source cleanup

0.2.0 (2017-09-19)
-----------------------
* Simplified and log of info and errors levels by removing logLevel options.
* Improvements to documentation.

0.1.3 (2017-06-13)
------------------
* Documentation fixes

0.1.2 (2017-06-11)
------------------
* First public release on PyPI.
