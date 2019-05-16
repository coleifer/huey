from huey.serializer import Serializer
from huey.tests.base import BaseTestCase


class TestSerializer(BaseTestCase):
    def test_serialize(self):
        serializer = Serializer()
        data = 1
        serialized_data = serializer.serialize(data)
        self.assertEqual(serializer.deserialize(serialized_data), data)

        serializer = Serializer(compression=True)
        serialized_data = serializer.serialize(data)
        self.assertEqual(serializer.deserialize(serialized_data), data)
