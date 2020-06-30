import os
from setuptools import setup, find_packages


with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as fh:
    readme = fh.read()

extras_require = {
    'backends': ['redis>=3.0.0'],
    'redis': ['redis>=3.0.0'],
}

setup(
    name='huey',
    version=__import__('huey').__version__,
    description='huey, a little task queue',
    long_description=readme,
    author='Charles Leifer',
    author_email='coleifer@gmail.com',
    url='http://github.com/coleifer/huey/',
    packages=find_packages(),
    extras_require=extras_require,
    package_data={
        'huey': [
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    test_suite='runtests.collect_tests',
    entry_points={
        'console_scripts': [
            'huey_consumer = huey.bin.huey_consumer:consumer_main'
        ]
    },
    scripts=['huey/bin/huey_consumer.py'],
)
