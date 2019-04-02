## Flask example

Minimal example of using Huey with Flask. Displays a form that accepts user
input and then enqueues a task with the form value when the form is submitted.

To try out the example:

* Run ``./run_webapp.sh`` then browse to http://localhost:5000/
* In second terminal, ``./run_huey.sh`` to run the consumer.

**Important**: note that the tasks and views are imported in the `main.py`,
which serves as the application entry-point. This is because any functions
decorated with `@huey.task()` need to be imported to be registered with the
huey instance. Similarly, we need to import the views so that our view function
is registered with the Flask application.
