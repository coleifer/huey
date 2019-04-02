from flask import Flask
from huey import RedisHuey


DEBUG = True
SECRET_KEY = 'shhh, secret'

app = Flask(__name__)
app.config.from_object(__name__)

huey = RedisHuey()
