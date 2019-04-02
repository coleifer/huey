from app import app
from app import huey
import tasks  # Import tasks so they are registered with Huey instance.
import views  # Import views so they are registered with Flask app.


if __name__ == '__main__':
    app.run()
