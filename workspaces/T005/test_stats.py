import unittest

from stats import mean


class TestStats(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([2, 4, 6]), 4)


if __name__ == "__main__":
    unittest.main()
