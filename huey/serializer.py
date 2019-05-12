import hashlib
import hmac
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


# identical to django.utils.crypto.constant_time_compare
def _constant_time_compare(val1, val2):
    """Return True if the two strings are equal, False otherwise."""
    return hmac.compare_digest(val1, val2)


class SignedSerializer(Serializer):
    def __init__(self, secret="", salt="huey", **kwargs):
        super().__init__(**kwargs)

        if not secret:
            raise ConfigurationError("A secret is required")

        if not salt:
            raise ConfigurationError("A salt is required")

        self.secret = secret.encode("utf-8")
        self.salt = salt.encode("utf-8")

        # if you change the separator, make sure it doesn't contain
        # any of [a-zA-Z0-9]
        self.separator = b":"

    def _signature(self, message: bytes):
        # same key derivation as django.utils.crypto.salted_hmac
        key = hashlib.sha1(self.salt + self.secret).digest()
        signature = hmac.new(key, msg=message, digestmod=hashlib.sha1)

        # we need to make sure that our digest can't contain the separator
        return signature.hexdigest().encode("utf-8")

    def _sign(self, message: bytes) -> bytes:
        signature = self._signature(message)
        return message + self.separator + signature

    def _unsign(self, signed_value: bytes) -> bytes:
        if self.separator not in signed_value:
            raise ValueError('Separator "%s" not found in value' % self.separator)

        value, sig = signed_value.rsplit(self.separator, 1)

        if _constant_time_compare(sig, self._signature(value)):
            return value

        raise ValueError('Signature "%s" does not match' % sig)

    def _serialize(self, data):
        serialized = super()._serialize(data)
        return self._sign(serialized)

    def _deserialize(self, data):
        unsigned = self._unsign(data)
        return super()._deserialize(unsigned)
