from flask import Flask, render_template, request
from svalid import svalid
from mock import patch

app = Flask(__name__)

def amicreate(ami):
	pass

@app.route('/', methods=['GET', 'POST'])
def frontpage():
	if request.method == 'POST':
		if request.form['create']:
			amicreate(request.form['ami'])

	return render_template('index.html')

import unittest

class FrontendTest(unittest.TestCase):
	def setUp(self):
		self.app = app.test_client(self)

	def test_index(self):
		tester = self.app

		# That a request for the root resource
		response = tester.get('/')

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns valid HTML
		self.assertTrue(svalid(response.data))

	@patch('frontend.amicreate')
	def test_create(self, ac):
		tester = self.app
		ami = 'foobar'

		# That a create request
		response = tester.post('/', data=dict(ami=ami, create='create'))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns valid HTML
		self.assertTrue(svalid(response.data))

		# and that amicreate was called
		ac.assert_called_once_with(ami)
