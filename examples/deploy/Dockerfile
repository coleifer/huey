FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1

# Use the exec form (JSON array, no shell) so that signals are delivered
# to the consumer rather than to an intermediate shell. -g TERM makes the
# SIGTERM sent by "docker stop" a graceful shutdown. -t 55 interrupts
# still-running tasks before the stop grace period expires, so raise the
# grace period from its default of 10 to 60 (docker stop -t 60, or
# stop_grace_period in compose).
CMD ["huey_consumer", "my_app.huey", "-w", "4", "-k", "thread", "-g", "TERM", "-t", "55"]
