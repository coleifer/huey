try:
    import gzip
except ImportError:
    gzip = None
import pickle

from huey.exceptions import ConfigurationError


class Serializer(object):
    def __init__(self, compression=False, compression_level=6):
        self.comp = compression
        self.comp_level = compression_level
        if self.comp and gzip is None:
            raise ConfigurationError('Cannot enable compression, gzip module '
                                     'not found.')

    def _serialize(self, data):
        return pickle.dumps(data, pickle.HIGHEST_PROTOCOL)

    def _deserialize(self, data):
        return pickle.loads(data)

    def serialize(self, data):
        data = self._serialize(data)
        return gzip.compress(data, self.comp_level) if self.comp else data

    def deserialize(self, data):
        return self._deserialize(gzip.decompress(data) if self.comp else data)
