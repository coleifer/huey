try:
    import gzip
except ImportError:
    gzip = None
try:
    import zlib
except ImportError:
    zlib = None
import pickle
import sys

from huey.exceptions import ConfigurationError


if gzip is not None:
    if sys.version_info[0] > 2:
        gzip_compress = gzip.compress
        gzip_decompress = gzip.decompress
    else:
        from io import BytesIO

        def gzip_compress(data, comp_level):
            buf = BytesIO()
            fh = gzip.GzipFile(fileobj=buf, mode='wb',
                               compresslevel=comp_level)
            fh.write(data)
            fh.close()
            return buf.getvalue()

        def gzip_decompress(data):
            buf = BytesIO(data)
            fh = gzip.GzipFile(fileobj=buf, mode='rb')
            try:
                return fh.read()
            finally:
                fh.close()


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
            if self.use_zlib:
                data = zlib.compress(data, self.comp_level)
            else:
                data = gzip_compress(data, self.comp_level)
        return data

    def deserialize(self, data):
        if self.comp:
            if self.use_zlib:
                data = zlib.decompress(data)
            else:
                data = gzip_decompress(data)
        return self._deserialize(data)
