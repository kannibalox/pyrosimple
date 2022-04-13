Installation Guide
==================

Installing from PyPI
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    pip install --user pyrosimple
    # pip install --user 'pyrosimple[torque]' # Optional dependencies, for advanced features
    pyroadmin --version


Installing from source
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    # Poetry is used for package and dependency management: https://python-poetry.org/
    curl -sSL https://install.python-poetry.org | python3 -
    git clone git@github.com:kannibalox/pyrosimple.git
    cd pyrosimple
    poetry install
    pyroadmin --version

.. _`virtualenv`: https://virtualenv.pypa.io/en/latest/
.. _`user install`: https://pip.pypa.io/en/latest/user_guide/#user-installs
