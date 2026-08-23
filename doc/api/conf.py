"""Sphinx configuration for the TaskSAT API reference.

The generated HTML is written into ``website/static/api/`` (see the
``gen:api`` script in ``website/package.json``), from where Docusaurus copies
it verbatim into its build output. It is therefore published at
https://nasa-jpl.github.io/tasksat/api/ as part of the main documentation site.
"""

import os
import sys

# The modules in src/smt are flat (they use `from tasknet_ast import *`, not a
# package-relative import), so the directory itself must be on sys.path.
sys.path.insert(0, os.path.abspath('../../src/smt'))

# -- Project information -----------------------------------------------------

project = 'TaskSAT'
copyright = '2026, California Institute of Technology'
author = 'Klaus Havelund'

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',    # Google-style Args:/Returns: sections
    'sphinx.ext.viewcode',    # "[source]" links next to each entry
    'sphinx.ext.intersphinx',
]

intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}

# Docstrings in this codebase use Markdown-ish single backticks. In reStructured-
# Text the default role for `foo` is "title reference" (italics); make it code.
default_role = 'literal'

exclude_patterns = ['_build']

# -- Autodoc -----------------------------------------------------------------

autodoc_member_order = 'bysource'
autodoc_typehints = 'description'
autodoc_default_options = {
    'members': True,
    # Private (_-prefixed) members are documented too. The usual reason to hide
    # them - keeping a library's public contract separate from its internals -
    # does not apply here: TaskSAT has no external API consumers, and 36% of the
    # code is private, concentrated in precisely the modules a reader comes for
    # (tasknet_smt is 69% private, and its _encode_* methods ARE the encoding).
    # Dunders remain excluded (that is the separate 'special-members' option).
    'private-members': True,
    # Undocumented members are included so the API surface is complete: e.g.
    # tasknet_ast.py defines 51 dataclasses of which 15 carry docstrings, and
    # the field lists are worth showing regardless.
    'undoc-members': True,
    'show-inheritance': True,
}


def _skip_ply(app, what, name, obj, skip, options):
    """Hide PLY's generated-grammar plumbing from the API docs.

    The ``p_*`` (parser) and ``t_*`` (lexer) functions in ``tasknet_parser``
    carry BNF productions in their docstrings rather than prose - 221 of them.
    The grammar is already published on the Formal Grammar page, generated from
    the same source by ``src/smt/gen_grammar_doc.py``.
    """
    if name.startswith(('p_', 't_')):
        return True
    return skip


def setup(app):
    app.connect('autodoc-skip-member', _skip_ply)


# -- HTML output -------------------------------------------------------------

html_theme = 'furo'
html_title = 'TaskSAT API'
html_static_path = []
