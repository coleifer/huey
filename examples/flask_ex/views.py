from flask import render_template
from flask import request

from app import app
from tasks import example_task


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST' and request.form.get('n'):
        n = request.form['n']

        # Enqueue our task, the consumer will pick it up and run it.
        example_task(n)
        message = 'Enqueued example_task(%s) - see consumer output' % n
    else:
        message = None

    return render_template('home.html', message=message)
