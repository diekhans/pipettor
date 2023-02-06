.. :changelog:

History
=======

0.8.0 (2023-02-05)
-----------------
* make most optional arguments require keyword form to help prevent errors, especially if open() options are assumed
* added more functions to make Popen objects file-like objects

0.7.0 (2023-01-06)
-----------------
* don't fail if invalid UTF-8 characters are written to capture stderr

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
