# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
# author: adefossez
# Inspired from https://github.com/kennethreitz/setup.py

from pathlib import Path

from setuptools import setup


NAME = 'demucs'
DESCRIPTION = 'Music source separation in the waveform domain.'

URL = 'https://github.com/facebookresearch/demucs'
EMAIL = 'defossez@fb.com'
AUTHOR = 'Alexandre Défossez'
REQUIRES_PYTHON = '>=3.8.0'

HERE = Path(__file__).parent

# Get version without explicitely loading the module.
for line in open('demucs/__init__.py'):
    line = line.strip()
    if '__version__' in line:
        context = {}
        exec(line, context)
        VERSION = context['__version__']


def load_requirements(name):
    required = [i.strip() for i in open(HERE / name)]
    required = [i for i in required if not i.startswith('#')]
    return required


REQUIRED = load_requirements('requirements_minimal.txt')
ALL_REQUIRED = load_requirements('requirements.txt')

try:
    with open(HERE / "README.md", encoding='utf-8') as f:
        long_description = '\n' + f.read()
except FileNotFoundError:
    long_description = DESCRIPTION

setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author=AUTHOR,
    author_email=EMAIL,
    python_requires=REQUIRES_PYTHON,
    url=URL,
    packages=['demucs'],
    extras_require={
        'dev': ALL_REQUIRED,
    },
    install_requires=REQUIRED,
    include_package_data=True,
    entry_points={
        'console_scripts': ['demucs=demucs.separate:main'],
    },
    license='MIT License',
    classifiers=[
        # Trove classifiers
        # Full list: https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'License :: OSI Approved :: MIT License',
        'Topic :: Multimedia :: Sound/Audio',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
    ],
)
