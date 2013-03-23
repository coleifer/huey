# Overview

The purpose of this example is to show how to enqueue commands, wait for
the results and then enqueue another set of commands.

This example makes requests to the yahoo and google search services to
simulate web crawler behavior.

## Run

Install dependencies:

    pip install -r requirements.txt

In one terminal:

    python consume.py

In another terminal:

    python produce.py
