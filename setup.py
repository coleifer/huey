from setuptools import setup, find_packages

setup(
    name='huey',
    packages=find_packages(),
    scripts=['huey/bin/huey_consumer.py'])
