FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1

# "docker stop" sends SIGTERM by default, which huey treats as "stop
# immediately, interrupting any running tasks". Huey's graceful-shutdown
# signal is INT.
STOPSIGNAL SIGINT

# Use the exec form (JSON array, no shell) so that signals are delivered
# to the consumer rather than to an intermediate shell.
CMD ["huey_consumer", "my_app.huey", "-w", "4", "-k", "thread"]
