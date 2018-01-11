import os
from setuptools import setup, find_packages


with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as fh:
    readme = fh.read()

extras_require = {
    'backends': ('peewee', "redis"),
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
    ],
    test_suite='runtests.runtests',
    entry_points={
        'console_scripts': [
            'huey_consumer = huey.bin.huey_consumer:consumer_main'
        ]
    },
    scripts=['huey/bin/huey_consumer.py'],
)
