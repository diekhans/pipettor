Pipettor Library
================


Function Interface
------------------
.. autofunction:: pipettor.run

.. autofunction:: pipettor.runout

.. autofunction:: pipettor.runlex

.. autofunction:: pipettor.runlexout
   

Pipeline Classes
----------------
.. autoclass:: pipettor.Pipeline
   :members:
   :undoc-members:
   :inherited-members:
      
.. autoclass:: pipettor.Popen
   :members:
   :undoc-members:
   :inherited-members:
                  

Process I/O Classes
-------------------
.. autoclass:: pipettor.DataReader
   :members:
   :undoc-members:
   :inherited-members:
   :exclude-members: get_child_read_fd,  get_child_write_fd
   
.. autoclass:: pipettor.DataWriter
   :members:
   :undoc-members:
   :inherited-members:
   :exclude-members: get_child_read_fd,  get_child_write_fd
   
.. autoclass:: pipettor.File
   :members:
   :undoc-members:
   :inherited-members:
   :exclude-members: get_child_read_fd,  get_child_write_fd
  

Logging Control
---------------

.. autodata:: pipettor.processes.LOGGER_NAME

.. autofunction:: pipettor.setDefaultLogging

.. autofunction:: pipettor.setDefaultLogger
   
.. autofunction:: pipettor.getDefaultLogger

.. autofunction:: pipettor.setDefaultLogLevel

.. autofunction:: pipettor.getDefaultLogLevel


Exceptions
----------
.. autoclass:: pipettor.PipettorException
   :members:
   :undoc-members:
   
.. autoclass:: pipettor.ProcessException
   :members:
   :undoc-members:
   
