from setuptools import setup, find_packages

setup(
    name='huey',
    packages=find_packages(),
    entry_points={'console_scripts': ['huey_consumer= huey.bin.huey_consumer:consumer_main']})
