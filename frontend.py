from flask import Flask, render_template, request, g
from svalid import svalid
from mock import patch

import lycan.datamodels as openc2
from lycan.message import OpenC2Command
from lycan.serializations import OpenC2MessageEncoder

import pha
import json
import uuid

CREATE = 'create'
ec2target = 'com.newcontext:awsec2'

app = Flask(__name__)

class AWSOpenC2Proxy(object):
	def __init__(self):
		self._pending = {}
		self._ids = []

	def amicreate(self, ami):
		cmd = OpenC2Command(action=CREATE, target=ec2target)
		cmduuid = str(uuid.uuid4())
		cmd.modifiers.command_id = cmduuid

		self._pending[cmduuid] = cmd

		msg = _seropenc2(cmd)
		openc2_publish(msg)

	def ec2ids(self):
		return self._ids

	def testfun(self):
		return 'testfun'

	def __contains__(self, item):
		return item in self._pending

for i in (x for x in dir(AWSOpenC2Proxy) if x[0] != '_'):
	# This extra function call seems unneeded, but it is required
	# because i gets late binding, and if we it in the outside, all
	# functions get the same i.  Python doesn't support default named
	# args that are not possition overrideable.  The additional function
	# provides the scope to properly bind i.
	def genfun(i):
		return lambda *args, **kwargs: getattr(get_ec2(), i)(*args, **kwargs)

	locals()[i] = genfun(i)

def get_ec2():
	if not hasattr(g, 'ec2'):
		g.ec2 = AWSOpenC2Proxy()

	return g.ec2

def _selfpatch(name):
	return patch('%s.%s' % (__name__, name))

def _seropenc2(msg):
	return json.dumps(msg, cls=OpenC2MessageEncoder)

def openc2_publish(oc2msg):
	raise NotImplementedError

@app.route('/', methods=['GET', 'POST'])
def frontpage():
	if request.method == 'POST':
		if request.form['create']:
			amicreate(request.form['ami'])

	return render_template('index.html', ec2ids=ec2ids())

import unittest

class FrontendTest(unittest.TestCase):
	def setUp(self):
		self.test_client = app.test_client(self)
		app.config['SNS_TOPIC'] = 'sns_topic'

	@_selfpatch('AWSOpenC2Proxy.ec2ids')
	def test_index(self, ec2idmock):
		tester = self.test_client

		ec2idmock.return_value = [ 'ec2ida', 'ec2idb' ]

		# That a request for the root resource
		response = tester.get('/')

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns valid HTML
		self.assertTrue(svalid(response.data))

		spec = pha.html(pha.option("ec2ida"), pha.option("ec2idb"))

		results = pha.html_match(spec, response.data)
		self.assertTrue(results.passed)

	@_selfpatch('AWSOpenC2Proxy.amicreate')
	def test_create(self, ac):
		tester = self.test_client
		ami = 'foobar'

		# That a create request
		response = tester.post('/', data=dict(ami=ami, create='create'))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns valid HTML
		self.assertTrue(svalid(response.data))

		# and that amicreate was called
		ac.assert_called_once_with(ami)

class InterlFuns(unittest.TestCase):
	def test_created(self):
		self.assertTrue(callable(amicreate))
		with app.app_context():
			self.assertEqual(testfun(), 'testfun')

	@patch('uuid.uuid4')
	@_selfpatch('openc2_publish')
	def test_ec2funs(self, oc2p, uuid):
		with app.app_context():
			ami = 'foo'

			ec2 = get_ec2()

			cmduuid = 'someuuid'
			uuid.return_value = cmduuid
			# That when amicreate is called
			ec2.amicreate(ami)

			# that it gets published
			oc2p.assert_called_once_with('{"action": "create", "modifiers": {"command_id": "someuuid"}, "target": {"type": "com.newcontext:awsec2"}}')

			# and that it's in pending
			self.assertIn(cmduuid, ec2)
