
import os
import sys

project = 'Multi-Layer Role-Playing Framework'
copyright = '2024, WangM'
author = 'WangM'
release = '0.1'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx_rtd_theme',
    'sphinx.ext.graphviz',
]

templates_path = ['_templates']
exclude_patterns = []

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# PDF/LaTeX Configuration
latex_engine = 'xelatex'
latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '11pt',
    'preamble': r'''
        \usepackage{xeCJK}
        \usepackage{indentfirst}
        \setlength{\parindent}{2em}
        \setCJKmainfont{PingFang SC}
        \setCJKsansfont{PingFang SC}
        \setCJKmonofont{PingFang SC}
    ''',
}
