import unittest
from jra_pdf_archive import dbconnect
from verify_and_promote import audit,promote
class Tests(unittest.TestCase):
 def test_empty(self):
  self.assertEqual(audit(dbconnect(':memory:'))['documents_checked'],0)
 def test_missing_pdf(self):
  with self.assertRaises(ValueError):promote(dbconnect(':memory:'),2025,'001',18)
 def test_expected_count(self):
  with self.assertRaises(ValueError):promote(dbconnect(':memory:'),2025,'001',0)
