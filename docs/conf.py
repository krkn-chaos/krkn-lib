# -*- coding: utf-8 -*-

import sys
import os

sys.path.insert(0, os.path.abspath("extensions"))

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.ifconfig",
]

todo_include_todos = True
templates_path = ["_templates"]
source_suffix = ".rst"
master_doc = "modules"
exclude_patterns = []
add_function_parentheses = True
# add_module_names = True
# A list of ignored prefixes for module index sorting.
# modindex_common_prefix = []

project = "Kubernetes client library helper for Python"
copyright = "Arcalot Contributors "

version = ""
release = ""

# -- Options for HTML output

html_theme = "classic"
html_theme_path = ["themes"]
html_title = "Kubernetes library for Kraken"
# html_short_title = None
# html_logo = None
# html_favicon = None
html_static_path = ["_static"]
html_domain_indices = False
html_use_index = False
html_show_sphinx = False
htmlhelp_basename = "KrknKubernetesLibDoc"
html_show_sourcelink = False


# -- Options for Code Examples output

code_example_dir = "code-example"
code_add_python_path = ["../py"]


def skip(app, what, name, obj, would_skip, options):
    if name == "__init__":
        return False
    return would_skip


def setup(app):
    from sphinx.util.texescape import tex_replacements

    app.add_css_file("krkn-style.css")
    app.connect("autodoc-skip-member", skip)
    tex_replacements += [
        ("♮", "$\\natural$"),
        ("ē", "\=e"),  # NOQA
        ("♩", "\quarternote"),  # NOQA
        ("↑", "$\\uparrow$"),
    ]
