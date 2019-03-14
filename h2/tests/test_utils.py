import unittest

from h2.utils import reraise_as


class MyException(Exception): pass


class TestReraiseAs(unittest.TestCase):
    def test_wrap_exception(self):
        def raise_keyerror():
            try:
                {}['huey']
            except KeyError as exc:
                reraise_as(MyException)

        self.assertRaises(MyException, raise_keyerror)
        try:
            raise_keyerror()
        except MyException as exc:
            self.assertEqual(str(exc), "KeyError: 'huey'")
        else:
            raise AssertionError('MyException not raised as expected.')
