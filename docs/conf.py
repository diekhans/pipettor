#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os.path as osp

# Get the project root dir, which is the parent dir of this file
project_root = osp.normpath(osp.abspath(osp.join(osp.dirname(__file__), '..')))

# Insert the project root dir src as the first element in the PYTHONPATH.
# This lets us ensure that the source package is imported, and that its
# version is used.
sys.path.insert(0, osp.join(project_root, "lib"))

import pipettor

# -- General configuration ---------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'sphinx.ext.viewcode',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
]
autosummary_generate = True

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix of source filenames.
source_suffix = '.rst'

# The encoding of source files.
#source_encoding = 'utf-8-sig'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = u'pipettor'
copyright = u'2015, Mark Diekhans'

# The version info for the project you're documenting, acts as replacement
# for |version| and |release|, also used in various other places throughout
# the built documents.
#
# The short X.Y version.
version = pipettor.__version__
# The full version, including alpha/beta/rc tags.
release = pipettor.__version__

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = [
    '_build',
]

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
add_module_names = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'


# -- Options for HTML output -------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = 'default'

# Add any paths that contain custom static files (such as style sheets)
# here, relative to this directory. They are copied after the builtin
# static files, so a file named "default.css" will overwrite the builtin
# "default.css".
#html_static_path = ['_static']
html_static_path = []


# Output file base name for HTML help builder.
htmlhelp_basename = 'pipettordoc'


# -- Options for LaTeX output ------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #'papersize': 'letterpaper',

    # The font size ('10pt', '11pt' or '12pt').
    #'pointsize': '10pt',

    # Additional stuff for the LaTeX preamble.
    #'preamble': '',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass
# [howto/manual]).
latex_documents = [
    ('index', 'pipettor.tex',
     u'pipettor Documentation',
     u'Mark Diekhans', 'manual'),
]
# -- Options for manual page output ------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'pipettor',
     u'pipettor Documentation',
     [u'Mark Diekhans'], 1)
]

# If true, show URL addresses after external links.
# -- Options for Texinfo output ----------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    ('index', 'pipettor',
     u'pipettor Documentation',
     u'Mark Diekhans',
     'pipettor',
     'Robust, easy to use Python package for running Unix process pipelines.',
     'Miscellaneous'),
]


# -- Other Options ----------------------------------------

# Don't repeat class name on members in TOC
toc_object_entries_show_parents = "hide"
