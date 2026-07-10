import os
import sys

extensions = [
    'sphinx.ext.autodoc',
    'sphinx_rtd_theme',
]

project = 'huey'
copyright = '2013, charles leifer'

sys.path.insert(0, os.path.realpath(os.path.dirname(os.path.dirname(__file__))))
from huey import __version__
version = release = __version__

exclude_patterns = ['_build']
pygments_style = 'sphinx'

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# Extra files copied to the root of the HTML build, e.g. llms.txt, served
# by readthedocs from the domain root (huey.readthedocs.io/llms.txt).
html_extra_path = ['extras']
