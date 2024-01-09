#!/bin/sh
echo "HUEY CONSUMER"
echo "-------------"
echo "In another terminal, run 'python main.py'"
echo "Stop the consumer using Ctrl+C"
PYTHONPATH=".:$PYTHONPATH"
export PYTHONPATH
WORKER_CLASS=${1:-thread}
export WORKER_CLASS
python ../../huey/bin/huey_consumer.py main.huey --workers=4 -k $WORKER_CLASS -S
