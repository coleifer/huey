Production deployment configurations for the huey consumer: systemd,
supervisord, Docker and Docker Compose.

These files are included verbatim in the documentation -- see the
"Deploying to Production" document at https://huey.readthedocs.io/ for
the full discussion of each, including Kubernetes and PaaS notes and a
production checklist.

The one thing to get right: huey shuts down gracefully on `SIGINT` and
treats `SIGTERM` as "stop immediately, interrupting running tasks", while
nearly every process supervisor defaults to stopping processes with
`SIGTERM`. Each config here sets the stop signal to `INT` accordingly.
