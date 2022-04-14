Installation Guide
==================

Installing from PyPI
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    pip install --user pyrosimple
    # pip install --user 'pyrosimple[torque]' # Optional dependencies, for advanced features
    pyroadmin --version

A `virtualenv`_ can be used instead of the `user install`_ if desired:

.. code-block:: bash

    pip install --user virtualenv
    virtualenv ~/.pyrosimple/venv
    source ~/.pyrosimple/venv/bin/activate
    pip install pyrosimple
    # pip install 'pyrosimple[torque]' # Optional dependencies, for advanced features
    pyroadmin --version

Installing from source
^^^^^^^^^^^^^^^^^^^^^^
`Poetry`_ is used for package and dependency management:

.. code-block:: bash

    curl -sSL https://install.python-poetry.org | python3 -
    git clone git@github.com:kannibalox/pyrosimple.git
    cd pyrosimple
    poetry install
    pyroadmin --version

.. _`virtualenv`: https://virtualenv.pypa.io/en/latest/
.. _`user install`: https://pip.pypa.io/en/latest/user_guide/#user-installs
.. _`Poetry`: https://python-poetry.org/
