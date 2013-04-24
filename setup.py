#!/usr/bin/env python3

from distutils.core import setup

setup(name='smon',
      version='1.1',
      author="Kandalintsev Alexandre",
      author_email='spam@messir.net',
      license="GPLv3",
      description="reliable server monitoring daemon",
      scripts=['smon.py'],
      py_modules=["bottle"],
      data_files=[('/usr/lib/systemd/system', ['smon.service'])]
)
