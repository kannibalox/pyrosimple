Migrating from pyrocore
=======================

*pyrosimple* aims to be backwards compatible with the pyroscope tools, however due
to the deep level of customization possible not everything can be used directly.

Configuration
-------------

The easiest thing to do is to copy your existing configuration to pyrosimple's dedicated folder

.. code-block:: bash

    cp -r ~/.pyroscope ~/.config/pyrosimple

Edit the config files to use ``pyrosimple`` instead of ``pyrocore``
