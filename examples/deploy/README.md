Production deployment configurations for the huey consumer: systemd,
supervisord, Docker and Docker Compose.

These files are included verbatim in the documentation. See the
"Deploying to Production" document at https://huey.readthedocs.io/ for
the full discussion of each, including Kubernetes and PaaS notes and a
production checklist.

For historical reasons huey shuts down gracefully on `SIGINT` and treats
`SIGTERM` as "stop immediately, interrupting running tasks". Most process
supervisors stop processes with `SIGTERM`, so each config here runs the
consumer with `-g TERM`, which makes `SIGTERM` the graceful signal.
Alternatively, leave the consumer's signals alone and set the supervisor's
stop signal to `INT`.

Each config also passes `-t 55` (`--shutdown-timeout`) with a 60 second
supervisor deadline, so tasks that cannot finish in time are interrupted
by huey, emitting `SIGNAL_INTERRUPTED`, rather than lost to `SIGKILL`.
