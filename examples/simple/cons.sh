#!/bin/bash
echo "HUEY CONSUMER"
echo "-------------"
echo "In another terminal, run 'python main.py'"
echo "Stop the consumer using Ctrl+C"
PYTHONPATH=.:$PYTHONPATH
python ../../huey/bin/huey_consumer.py main.huey --threads=2
