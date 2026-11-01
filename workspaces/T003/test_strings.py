import unittest

from strings import is_palindrome


class TestStrings(unittest.TestCase):
    def test_palindrome(self):
        self.assertTrue(is_palindrome("level"))

    def test_not_palindrome(self):
        self.assertFalse(is_palindrome("abc"))


if __name__ == "__main__":
    unittest.main()
