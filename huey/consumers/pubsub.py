import logging
import redis
try:
    import simplejson as json
except ImportError:
    import json

class BasePubSub(object):
    """
        Base Implentation for a PubSub component for Consumers
    """
    def __init__(self, **connection):
        """
            Set up connections here
        """
        self.connection = connection

    def send_message(self, task_id=None, task_display_name=None, status=None, result=None):
        """
            Send meaningfull task data here
        """
        raise NotImplementedError

    def make_message(self,task_id=None, task_display_name=None, status=None, result=None):
        mssg = {
            'task_name':task_display_name,
            'task_id':task_id,
            'status':status,
            'result':result,
        }
        return mssg


class DummyPubSub(BasePubSub):

    def __init__(self, name, **connection):
        self.conn = logging.getLogger(name)
        self.conn.setLevel(logging.INFO)
        super(DummyPubSub, self).__init__(**connection)

    def send_message(self, task_id=None, task_display_name=None, status=None, result=None):
        self.conn.info(self.make_message(task_id, task_display_name, status, result))


class RedisPubSub(BasePubSub):
    """
        Uses Redis PUBLISH to place messages
        conn = {
            'host':'localhost',
            'port':6379,
            'channel':'defaultmssgqueue'
            'db' 0
        }
    """
    def __init__(self, **connection):

        # defaults
        self.redis_conn = {}
        self.redis_conn['host'] = connection.get('host', 'localhost')
        self.redis_conn['port'] = connection.get('port', 6379)
        self.redis_conn['db'] = connection.get('db', 0)

        self.conn = redis.Redis(**self.redis_conn)
        self.channel = connection.get('channel', 'hueypubsubchannel')

        super(RedisPubSub, self).__init__(**connection)

    def send_message(self, task_id=None, task_display_name=None, status=None, result=None):
        """ Serialize task's info as json then PUB it"""
        self.conn.publish(self.channel, json.dumps(self.make_message(task_id, task_display_name, status, result)))

