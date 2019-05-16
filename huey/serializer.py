try:
    import gzip
except ImportError:
    gzip = None
try:
    import zlib
except ImportError:
    zlib = None
import pickle

from huey.exceptions import ConfigurationError


class Serializer(object):
    def __init__(self, compression=False, compression_level=6, use_zlib=False):
        self.comp = compression
        self.comp_level = compression_level
        self.use_zlib = use_zlib
        if self.comp:
            if self.use_zlib and zlib is None:
                raise ConfigurationError('use_zlib specified, but zlib module '
                                         'not found.')
            elif gzip is None:
                raise ConfigurationError('gzip module required to enable '
                                         'compression.')

    def _serialize(self, data):
        return pickle.dumps(data, pickle.HIGHEST_PROTOCOL)

    def _deserialize(self, data):
        return pickle.loads(data)

    def serialize(self, data):
        data = self._serialize(data)
        if self.comp:
            compress = zlib.compress if self.use_zlib else gzip.compress
            data = compress(data, self.comp_level)
        return data

    def deserialize(self, data):
        if self.comp:
            decompress = zlib.decompress if self.use_zlib else gzip.decompress
            data = decompress(data)
        return self._deserialize(data)
