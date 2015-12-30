#!/bin/bash
echo "HUEY CONSUMER"
echo "-------------"
echo "In another terminal, run 'python main.py'"
echo "Stop the consumer using Ctrl+C"
PYTHONPATH=.:$PYTHONPATH
python ../../huey/bin/huey_consumer.py main.huey --workers=4 -S 10 -k thread
