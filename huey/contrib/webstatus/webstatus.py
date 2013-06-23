#!/usr/bin/env python
from gevent.monkey import patch_all; patch_all()

import json
import optparse
import sys
import time
from functools import wraps

import gevent
from flask import Flask
from flask import render_template
from flask import request
from gevent.pywsgi import WSGIServer
from gevent.queue import Queue
from geventwebsocket.handler import WebSocketHandler
from redis import Redis


app = Flask(__name__)
host = '127.0.0.1'
port = 8555
queue = Queue()
redis = Redis()


def webstatus_app(environ, start_response):
    path = environ['PATH_INFO']
    if path == "/websocket":
        handle_websocket(environ['wsgi.websocket'])
    else:
        return app(environ, start_response)

@app.route('/')
def index():
    return render_template('index.html', port=port)

def green(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        gevent.spawn(fn, *args, **kwargs)
    return inner

@green
def listen(pubsub, websocket):
    template = app.jinja_env.get_template('message.html')
    while True:
        for message in pubsub.listen():
            channel = message['channel']
            try:
                data = json.loads(message['data'])
            except (ValueError, TypeError):
                pass
            else:
                websocket.send(template.render(
                    channel=channel,
                    data=data))

def handle_websocket(ws):
    pubsub = redis.pubsub()
    pubsub.psubscribe('*')
    listen(pubsub, ws)
    while True:
        message = ws.receive()
        if message is None:
            break
        else:
            message = json.loads(message)
            r  = 'I have received this message from you : %s' % message
            r += '<br>Glad to be your webserver.'
            ws.send(json.dumps({'output': time.time()}))

def get_option_parser():
    global host, port
    usage = "Usage: %prog [options] channel1 channel2"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-H', '--host', dest='host', default=host)
    parser.add_option('-p', '--port', dest='port', default=port, type='int')
    parser.add_option('-d', '--debug', dest='debug', action='store_true')
    return parser


if __name__ == '__main__':
    parser = get_option_parser()
    options, args = parser.parse_args()
    host = options.host
    port = options.port

    server = WSGIServer(
        (host, port),
        webstatus_app,
        handler_class=WebSocketHandler)
    server.serve_forever()
