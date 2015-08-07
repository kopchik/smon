#!/usr/bin/env python3

from distutils.core import setup
from smon import __version__, PREFIX
from glob import glob

setup(name='smon',
      version=str(__version__),
      author="Kandalintsev Alexandre",
      author_email='spam@messir.net',
      license="GPLv3",
      description="reliable server monitoring daemon",
      scripts=['smon.py'],
      py_modules=["bottle", "libsmon"],
      data_files=[
        ('/usr/lib/systemd/system', ['smon.service']),
        (PREFIX+'/views', glob('views/*')),
        (PREFIX+'/static', glob('static/*')),
      ]
)
