import gevent
from gevent import socket
from gevent.pool import Pool
from gevent.server import StreamServer

from collections import defaultdict
from collections import deque
from collections import namedtuple
from io import BytesIO
from socket import error as socket_error
import datetime
import heapq
import logging
import optparse
import sys


logger = logging.getLogger(__name__)


class CommandError(Exception):
    def __init__(self, message):
        self.message = message
        super(CommandError, self).__init__()


class Disconnect(Exception): pass


"""
Protocol is based on Redis wire protocol.

Client sends requests as an array of bulk strings.

Server replies, indicating response type using the first byte:

* "+" - simple string
* "-" - error
* ":" - integer
* "$" - bulk string
* "*" - array

Simple strings: "+string content\r\n"  <-- cannot contain newlines

Error: "-Error message\r\n"

Integers: ":1337\r\n"

Bulk String: "$number of bytes\r\nstring data\r\n"

* Empty string: "$0\r\n\r\n"
* NULL: "$-1\r\n"

Array: "*number of elements\r\n...elements..."

* Empty array: "*0\r\n"

And a new data-type, dictionaries: "%number of elements\r\n...elements..."
"""
if sys.version_info[0] == 3:
    unicode = str
    basestring = (bytes, str)


def encode(s):
    if isinstance(s, unicode):
        return s.encode('utf-8')
    elif isinstance(s, bytes):
        return s
    else:
        return str(s).encode('utf-8')


def decode(s):
    if isinstance(s, unicode):
        return s
    elif isinstance(s, bytes):
        return s.decode('utf-8')
    else:
        return str(s)


Error = namedtuple('Error', ('message',))


class ProtocolHandler(object):
    def __init__(self):
        self.handlers = {
            b'+': self.handle_simple_string,
            b'-': self.handle_error,
            b':': self.handle_integer,
            b'$': self.handle_string,
            b'*': self.handle_array,
            b'%': self.handle_dict,
        }

    def handle_simple_string(self, socket_file):
        return socket_file.readline().rstrip(b'\r\n')

    def handle_error(self, socket_file):
        return Error(socket_file.readline().rstrip(b'\r\n'))

    def handle_integer(self, socket_file):
        number = socket_file.readline().rstrip(b'\r\n')
        if b'.' in number:
            return float(number)
        return int(number)

    def handle_string(self, socket_file):
        length = int(socket_file.readline().rstrip(b'\r\n'))
        if length == -1:
            return None
        length += 2
        return socket_file.read(length)[:-2]

    def handle_array(self, socket_file):
        num_elements = int(socket_file.readline().rstrip(b'\r\n'))
        return [self.handle_request(socket_file) for _ in range(num_elements)]

    def handle_dict(self, socket_file):
        num_items = int(socket_file.readline().rstrip(b'\r\n'))
        elements = [self.handle_request(socket_file)
                    for _ in range(num_items * 2)]
        return dict(zip(elements[::2], elements[1::2]))

    def handle_request(self, socket_file):
        first_byte = socket_file.read(1)
        if not first_byte:
            raise Disconnect()

        try:
            return self.handlers[first_byte](socket_file)
        except KeyError:
            raise ValueError('invalid request')

    def write_response(self, socket_file, data):
        buf = BytesIO()
        self._write(buf, data)
        buf.seek(0)
        socket_file.write(buf.getvalue())
        socket_file.flush()

    def _write(self, buf, data):
        if isinstance(data, bytes):
            buf.write(b'$%d\r\n%s\r\n' % (len(data), data))
        elif isinstance(data, unicode):
            bdata = data.encode('utf-8')
            buf.write(b'$%d\r\n%s\r\n' % (len(bdata), bdata))
        elif isinstance(data, (int, float)):
            buf.write(b':%d\r\n' % data)
        elif isinstance(data, Error):
            buf.write(b'-%s\r\n' % bytes(data.message, 'utf-8'))
        elif isinstance(data, (list, tuple)):
            buf.write(b'*%d\r\n' % len(data))
            for item in data:
                self._write(buf, item)
        elif isinstance(data, dict):
            buf.write(b'%%%d\r\n' % len(data))
            for key in data:
                self._write(buf, key)
                self._write(buf, data[key])
        elif data is None:
            buf.write(b'$-1\r\n')


class Shutdown(Exception): pass


class QueueServer(object):
    def __init__(self, host='127.0.0.1', port=31337, max_clients=64):
        self._host = host
        self._port = port
        self._max_clients = max_clients
        self._pool = Pool(max_clients)
        self._server = StreamServer(
            (self._host, self._port),
            self.connection_handler,
            spawn=self._pool)

        self._commands = self.get_commands()
        self._protocol = ProtocolHandler()

        self._kv = {}
        self._queues = defaultdict(deque)
        self._schedule = []

    def get_commands(self):
        timestamp_re = (r'(?P<timestamp>\d{4}-\d{2}-\d{2} '
                        '\d{2}:\d{2}:\d{2}(?:\.\d+)?)')
        return dict((
            # Queue commands.
            (b'ENQUEUE', self.queue_append),
            (b'DEQUEUE', self.queue_pop),
            (b'REMOVE', self.queue_remove),
            (b'FLUSH', self.queue_flush),
            (b'LENGTH', self.queue_length),

            # K/V commands.
            (b'SET', self.kv_set),
            (b'SETNX', self.kv_setnx),
            (b'GET', self.kv_get),
            (b'POP', self.kv_pop),
            (b'DELETE', self.kv_delete),
            (b'EXISTS', self.kv_exists),
            (b'MSET', self.kv_mset),
            (b'MGET', self.kv_mget),
            (b'MPOP', self.kv_mpop),
            (b'FLUSH_KV', self.kv_flush),
            (b'LENGTH_KV', self.kv_length),

            # Schedule commands.
            (b'ADD', self.schedule_add),
            (b'READ', self.schedule_read),
            (b'READ', self.schedule_read),
            (b'FLUSH_SCHEDULE', self.schedule_flush),
            (b'LENGTH_SCHEDULE', self.schedule_length),

            # Misc.
            (b'FLUSHALL', self.flush_all),
            (b'SHUTDOWN', self.shutdown),
        ))

    def queue_append(self, queue, value):
        self._queues[queue].append(value)
        return 1

    def queue_pop(self, queue):
        try:
            return self._queues[queue].popleft()
        except IndexError:
            pass

    def queue_remove(self, queue, value):
        try:
            self._queues[queue].remove(value)
        except ValueError:
            return 0
        else:
            return 1

    def queue_flush(self, queue):
        qlen = self.queue_length(queue)
        self._queues[queue].clear()
        return qlen

    def queue_length(self, queue):
        return len(self._queues[queue])

    def kv_set(self, key, value):
        self._kv[key] = value
        return 1

    def kv_setnx(self, key, value):
        if key in self._kv:
            return 0
        else:
            self._kv[key] = value
            return 1

    def kv_get(self, key):
        return self._kv.get(key)

    def kv_pop(self, key):
        return self._kv.pop(key, None)

    def kv_delete(self, key):
        if key in self._kv:
            del self._kv[key]
            return 1
        return 0

    def kv_exists(self, key):
        return 1 if key in self._kv else 0

    def kv_mset(self, *items):
        for idx in range(0, len(items), 2):
            self._kv[items[idx]] = items[idx + 1]
        return len(items) / 2

    def kv_mget(self, *keys):
        return [self._kv.get(key) for key in keys]

    def kv_mpop(self, *keys):
        return [self._kv.pop(key, None) for key in keys]

    def kv_flush(self):
        kvlen = self.kv_length()
        self._kv.clear()
        return kvlen

    def kv_length(self):
        return len(self._kv)

    def _decode_timestamp(self, timestamp):
        fmt = '%Y-%m-%d %H:%M:%S'
        if b'.' in timestamp:
            fmt = fmt + '.%f'
        try:
            return datetime.datetime.strptime(decode(timestamp), fmt)
        except ValueError:
            raise CommandError('Timestamp must be formatted Y-m-d H:M:S')

    def schedule_add(self, timestamp, data):
        dt = self._decode_timestamp(timestamp)
        heapq.heappush(self._schedule, (dt, data))
        return 1

    def schedule_read(self, timestamp=None):
        dt = self._decode_timestamp(timestamp)
        accum = []
        while self._schedule and self._schedule[0][0] <= dt:
            ts, data = heapq.heappop(self._schedule)
            accum.append(data)
        return accum

    def schedule_flush(self):
        schedulelen = self.schedule_length()
        self._schedule = []
        return schedulelen

    def schedule_length(self):
        return len(self._schedule)

    def flush_all(self):
        self._queues = defaultdict(deque)
        self.kv_flush()
        self.schedule_flush()
        return 1

    def shutdown(self):
        raise Shutdown('shutting down')

    def run(self):
        self._server.serve_forever()

    def connection_handler(self, conn, address):
        logger.info('Connection received: %s:%s' % address)
        socket_file = conn.makefile('rwb')
        while True:
            try:
                data = self._protocol.handle_request(socket_file)
            except Disconnect:
                logger.info('Client went away: %s:%s' % address)
                break

            try:
                resp = self.respond(data)
            except Shutdown:
                logger.info('Shutting down')
                self._protocol.write_response(socket_file, 1)
                raise KeyboardInterrupt()
            except CommandError as command_error:
                resp = Error(command_error.message)
            except Exception as exc:
                logger.exception('Unhandled error')
                resp = Error('Unhandled server error')

            self._protocol.write_response(socket_file, resp)

    def respond(self, data):
        if not isinstance(data, list):
            try:
                data = data.split()
            except:
                raise CommandError('Unrecognized request type.')

        if not isinstance(data[0], basestring):
            raise CommandError('First parameter must be command name.')

        command = data[0].upper()
        if command not in self._commands:
            raise CommandError('Unrecognized command: %s' % command)
        else:
            logger.debug('Received %s', decode(command))

        return self._commands[command](*data[1:])


class Client(object):
    def __init__(self, host='127.0.0.1', port=31337):
        self._host = host
        self._port = port
        self._socket = None
        self._fh = None
        self._protocol = ProtocolHandler()

    def connect(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((self._host, self._port))
        self._fh = self._socket.makefile('rwb')

    def close(self):
        self._socket.close()

    def execute(self, *args):
        self._protocol.write_response(self._fh, args)
        resp = self._protocol.handle_request(self._fh)
        if isinstance(resp, Error):
            raise CommandError(resp.message)
        return resp

    def enqueue(self, queue, data):
        return self.execute('ENQUEUE', queue, data)

    def dequeue(self, queue):
        return self.execute('DEQUEUE', queue)

    def unqueue(self, queue, data):
        return self.execute('REMOVE', queue, data)

    def queue_size(self, queue):
        return self.execute('LENGTH', queue)

    def flush_queue(self, queue):
        return self.execute('FLUSH', queue)

    def add_to_schedule(self, data, ts):
        return self.execute('ADD', str(ts), data)

    def read_schedule(self, ts):
        return self.execute('READ', str(ts))

    def schedule_size(self):
        return self.execute('LENGTH_SCHEDULE')

    def flush_schedule(self):
        return self.execute('FLUSH_SCHEDULE')

    def put_data(self, key, value):
        return self.execute('SET', key, value)
    set = put_data

    def peek_data(self, key):
        return self.execute('GET', key)
    get = peek_data

    def mget(self, *keys):
        return self.execute('MGET', *keys)

    def mset(self, __data=None, **kwargs):
        items = []
        if __data:
            for key in __data:
                items.append(key)
                items.append(__data[key])
        for key in kwargs:
            items.append(key)
            items.append(kwargs[key])
        return self.execute('MSET', *items)

    def mpop(self, *keys):
        return self.execute('MPOP', *keys)

    def pop_data(self, key):
        return self.execute('POP', key)

    def has_data_for_key(self, key):
        return self.execute('EXISTS', key)

    def put_if_empty(self, key, value):
        return self.execute('SETNX', key, value)

    def result_store_size(self):
        return self.execute('LENGTH_KV')

    def flush_results(self):
        return self.execute('FLUSH_KV')

    def flush_all(self):
        return self.execute('FLUSHALL')

    def shutdown(self):
        self.execute('SHUTDOWN')


def get_option_parser():
    parser = optparse.OptionParser()
    parser.add_option('-d', '--debug', action='store_true', dest='debug',
                      help='Log debug messages.')
    parser.add_option('-e', '--errors', action='store_true', dest='error',
                      help='Log error messages only.')
    parser.add_option('-H', '--host', default='127.0.0.1', dest='host',
                      help='Host to listen on.')
    parser.add_option('-m', '--max-clients', default=64, dest='max_clients',
                      help='Maximum number of clients.', type=int)
    parser.add_option('-p', '--port', default=31337, dest='port',
                      help='Port to listen on.', type=int)
    parser.add_option('-l', '--log-file', dest='log_file', help='Log file.')
    return parser


def configure_logger(options):
    logger.addHandler(logging.StreamHandler())
    if options.log_file:
        logger.addHandler(logging.FileHandler(options.log_file))
    if options.debug:
        logger.setLevel(logging.DEBUG)
    elif options.error:
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.INFO)


if __name__ == '__main__':
    options, args = get_option_parser().parse_args()

    from gevent import monkey; monkey.patch_all()
    configure_logger(options)

    server = QueueServer(host=options.host, port=options.port,
                         max_clients=options.max_clients)
    server.run()
