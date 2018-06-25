from flask import Flask, render_template, request, g, abort
from svalid import svalid
from mock import patch

import lycan.datamodels as openc2
from lycan.message import OpenC2Command, OpenC2Response
from lycan.serializations import OpenC2MessageEncoder, OpenC2MessageDecoder

import pha
import json
import uuid
import requests

CREATE = 'create'
ec2target = 'com.newcontext:awsec2'

app = Flask(__name__)

_instcmds = ('Query', 'Start', 'Stop', 'Delete')

class AWSOpenC2Proxy(object):
	def __init__(self):
		self._pending = {}
		self._ids = []

	def ec2ids(self):
		return self._ids

	def process_msg(self, msg):
		pass

	def _cmdpub(self, action, **kwargs):
		ocpkwargs = {}
		if 'meth' in kwargs:
			ocpkwargs['meth'] = kwargs.pop('meth')

		cmd = OpenC2Command(action=action, target=ec2target,
		    modifiers=kwargs)
		cmduuid = str(uuid.uuid4())
		cmd.modifiers.command_id = cmduuid

		self._pending[cmduuid] = cmd

		msg = _seropenc2(cmd)
		openc2_publish(msg, **ocpkwargs)

		return cmduuid

	def amicreate(self, ami):
		return self._cmdpub(CREATE, image=ami)

	def ec2query(self, inst):
		return self._cmdpub('query', instance=inst, meth='get')

	def ec2start(self, inst):
		return self._cmdpub('start', instance=inst)

	def ec2stop(self, inst):
		return self._cmdpub('stop', instance=inst)

	def ec2delete(self, inst):
		return self._cmdpub('delete', instance=inst)

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

def _deseropenc2(msg):
	return json.loads(msg, cls=OpenC2MessageDecoder)

def openc2_publish(oc2msg, meth='post'):
	app.logger.debug('publishing msg: %s' % `oc2msg`)

	msg = getattr(requests, meth)('http://localhost:5001/ec2', data=oc2msg)

	get_ec2().process_msg(msg)

	return msg

@app.route('/', methods=['GET', 'POST'])
def frontpage():
	if request.method == 'POST':
		if 'create' in request.form:
			amicreate(request.form['ami'])
		else:
			for i in ('query', 'start', 'stop', 'delete'):
				if i in request.form:
					f = globals()['ec2%s' % i]
					f(request.form['instance'])
					break
			else:
				abort(400)

	return render_template('index.html', ec2ids=ec2ids(), instcmds=_instcmds)

import unittest

class FrontendTest(unittest.TestCase):
	def setUp(self):
		self.test_client = app.test_client(self)

	@_selfpatch('AWSOpenC2Proxy.ec2ids')
	def test_index(self, ec2idmock):
		# the available ec2ids
		ec2idmock.return_value = [ 'ec2ida', 'ec2idb' ]

		# That a request for the root resource
		response = self.test_client.get('/')

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns valid HTML
		self.assertTrue(svalid(response.data))

		spec = pha.html(pha.option("ec2ida"), pha.option("ec2idb"))

		# and contains the two EC2 instance IDs
		results = pha.html_match(spec, response.data)
		self.assertTrue(results.passed)

	@_selfpatch('AWSOpenC2Proxy.amicreate')
	def test_create(self, ac):
		ami = 'foobar'

		# That a create request
		response = self.test_client.post('/', data=dict(ami=ami,
		    create='create'))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns valid HTML
		self.assertTrue(svalid(response.data))

		# and that amicreate was called
		ac.assert_called_once_with(ami)

	@_selfpatch('AWSOpenC2Proxy.process_msg')
	@patch('requests.get')
	@patch('requests.post')
	def test_oc2pub(self, mockpost, mockget, mockprocmsg):
		msg = 'foobar'
		retmsg = 'bleh'

		mockpost.return_value = retmsg

		with app.app_context():
			# That when a message is published
			r = openc2_publish(msg)

			# it returns the message
			self.assertEqual(r, retmsg)

			# and that it was passed to the actuator
			mockpost.assert_called_once_with(
			    'http://localhost:5001/ec2', data=msg)

			# That it was passed on to processing
			mockprocmsg.assert_called_once_with(retmsg)

			retmsg = 'othermsg'
			mockget.return_value = retmsg

			# That when a message is published w/ method get
			r = openc2_publish(msg, meth='get')

			# that it returns the correct results
			self.assertEqual(r, retmsg)

			# and that it was passed to the actuator
			mockget.assert_called_once_with(
			    'http://localhost:5001/ec2', data=msg)

	def test_badpost(self):
		# That a create request
		response = self.test_client.post('/', data=dict(bad='data',
		    rets='error'))

		# returns an error
		self.assertEqual(response.status_code, 400)

	def test_instfuns(self):
		inst = 'foobar'

		for i in _instcmds:
			il = i.lower()
			with _selfpatch('AWSOpenC2Proxy.ec2%s' % il) as fun:
				# That a request
				response = self.test_client.post('/',
				    data=dict(instance=inst, **{il: i}))

				# Is successful
				self.assertEqual(response.status_code, 200,
				    msg=(i, response.data))

				# and returns valid HTML
				self.assertTrue(svalid(response.data))

				# and that the function was called
				fun.assert_called_once_with(inst)

class InterlFuns(unittest.TestCase):
	@patch('uuid.uuid4')
	@_selfpatch('openc2_publish')
	def test_ec2create(self, oc2p, uuid):
		with app.app_context():
			ami = 'foo'

			cmduuid = 'someuuid'
			uuid.return_value = cmduuid

			# That when amicreate is called
			r = amicreate(ami)

			# That is returns the uuid
			self.assertEqual(r, cmduuid)

			# that it gets published
			oc2p.assert_called_once_with('{"action": "create", "modifiers": {"image": "foo", "command_id": "someuuid"}, "target": {"type": "com.newcontext:awsec2"}}')

			# and that it's in pending
			self.assertIn(cmduuid, get_ec2())

			# XXX - Test responses later
			#ec2inst = 'instid'

			#resp = OpenC2Response(source=ec2target, status='OK',
			#    results=ec2inst, cmdref=cmduuid)

			#msg = _seropenc2(resp)

			#openc2_recv(msg)

	@patch('uuid.uuid4')
	@_selfpatch('openc2_publish')
	def test_ec2funs(self, oc2p, uuid):
		with app.app_context():
			inst = 'foo'

			cmduuid = 'someuuid'
			uuid.return_value = cmduuid

			for i in _instcmds:
				il = i.lower()
				oc2p.reset_mock()

				# That when the function is called
				f = globals()['ec2%s' % il]
				f(inst)

				kwargs = {}
				if il == 'query':
					kwargs['meth'] = 'get'

				# that it gets published
				oc2p.assert_called_once_with('{"action": "%s", "modifiers": {"instance": "foo", "command_id": "someuuid"}, "target": {"type": "com.newcontext:awsec2"}}' % il, **kwargs)

				# and that it's in pending
				self.assertIn(cmduuid, get_ec2())
