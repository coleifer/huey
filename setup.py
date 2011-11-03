import os
from setuptools import setup, find_packages


setup(
    name='skew',
    version="0.1.0",
    description='a simple queue for python',
    author='Charles Leifer',
    author_email='coleifer@gmail.com',
    url='http://github.com/coleifer/skew/tree/master',
    packages=find_packages(),
    package_data = {
        'skew': [
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
    test_suite='runtests.runtests',
    scripts = ['skew/bin/skew_consumer.py'],
)
