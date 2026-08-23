TaskSAT API Reference
=====================

Reference documentation for the TaskSAT implementation, generated from the
docstrings in ``src/smt``.

TaskSAT is a domain-specific language and tool for modeling and verifying task
scheduling problems with rich temporal and resource constraints. This site
documents the *code*; for the *language* — installation, tutorial, manual,
grammar and the theory behind the SMT encoding — see the main documentation
site at https://nasa-jpl.github.io/tasksat/.

The verification pipeline
-------------------------

.. code-block:: text

   .tn file -> Parser -> AST -> Transformations -> Wellformedness
            -> SMT Encoding -> Z3 Solver -> Schedule / UNSAT

The modules below are grouped by their role in that pipeline.

.. toctree::
   :maxdepth: 2
   :caption: Modules

   pipeline
   visualization
   tooling

Indices
-------

* :ref:`genindex`
* :ref:`modindex`
