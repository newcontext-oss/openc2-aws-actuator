from html5validator.validator import Validator
import unittest
import tempfile
import logging

if True:
	l = logging.getLogger('html5validator.validator')
	l.addHandler(logging.StreamHandler())

class InvalidHTML(Exception):
	'''Invalid HTML Exception class.'''

	pass

def svalid(arg):
	'''Validate the passing in string to be valid HTML.  Returns True
	if the string is valid, otherwise raises the InvalidHTML exception.'''

	with tempfile.NamedTemporaryFile() as fp:
		fp.write(arg)
		fp.flush()

		i = Validator().validate([ fp.name])

		if i:
			raise InvalidHTML('%d errors' % i)

	return True

class SValidTest(unittest.TestCase):
	def test_svalid(self):
		self.assertTrue(svalid('<!DOCTYPE html><html><head><title>foo</title></head></html>'))

		self.assertRaises(InvalidHTML, svalid, '<html><head>foo')
