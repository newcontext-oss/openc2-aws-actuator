from html5validator.validator import Validator
import unittest
import tempfile
import logging

_QUICK = False

if True:
	l = logging.getLogger('html5validator.validator')
	l.addHandler(logging.StreamHandler())

class InvalidHTML(Exception):
	'''Invalid HTML Exception class.'''

	pass

def svalid(arg):
	'''Validate the passing in string to be valid HTML.  Returns True
	if the string is valid, otherwise raises the InvalidHTML exception.'''

	if _QUICK:
		return True

	with tempfile.NamedTemporaryFile() as fp:
		fp.write(arg)
		fp.flush()

		i = Validator().validate([ fp.name])

		if i:
			raise InvalidHTML('%d errors' % i)

	return True

class SValidTest(unittest.TestCase):
	def setUp(self):
		self.oldq = _QUICK

	def tearDown(self):
		global _QUICK
		_QUICK = self.oldq

	def test_svalid(self):
		# That when validating html
		global _QUICK
		_QUICK = False

		# valid HTML returns True
		self.assertTrue(svalid('<!DOCTYPE html><html><head><title>foo</title></head></html>'))

		# and invalid HTML raises an InvalidHTML exception
		self.assertRaises(InvalidHTML, svalid, '<html><head>foo')

	def test_quick(self):
		# That when disabling validation
		global _QUICK
		_QUICK = True

		# even invalid HTML returns True
		self.assertTrue(svalid('<html><head>foo'))
