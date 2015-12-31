from huey.tests.base import BaseTestCase
from huey.utils import wrap_exception


class MyException(Exception):
    pass


class TestWrapException(BaseTestCase):
    def test_wrap_exception(self):
        def raise_keyerror():
            try:
                {}['huey']
            except KeyError as exc:
                raise wrap_exception(MyException)

        self.assertRaises(MyException, raise_keyerror)
        try:
            raise_keyerror()
        except MyException as exc:
            self.assertEqual(str(exc), "KeyError: 'huey'")
        else:
            assert False
