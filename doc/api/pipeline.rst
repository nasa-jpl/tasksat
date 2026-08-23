Verification pipeline
=====================

The modules that take a ``.tn`` specification from source text to a schedule
(or a proof that none exists), in pipeline order.

``tasknet_ast``
---------------

.. automodule:: tasknet_ast

``tasknet_parser``
------------------

.. automodule:: tasknet_parser

.. note::

   The 221 PLY rule functions (``p_*``, ``t_*``) are omitted here: their
   docstrings are BNF productions rather than prose. The grammar they define is
   published, generated from the same source, on the
   `Formal Grammar <https://nasa-jpl.github.io/tasksat/docs/reference/grammar-formal>`_
   page.

``tasknet_transforms``
----------------------

.. automodule:: tasknet_transforms

``tasknet_wellformedness``
--------------------------

.. automodule:: tasknet_wellformedness

``tasknet_smt``
---------------

.. automodule:: tasknet_smt

``tasknet_realizability``
-------------------------

.. automodule:: tasknet_realizability

``tasknet_compositional``
-------------------------

.. automodule:: tasknet_compositional

``tasknet_verifier``
--------------------

.. automodule:: tasknet_verifier

``tasknet_printer``
-------------------

.. automodule:: tasknet_printer
