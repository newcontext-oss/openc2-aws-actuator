from flask import Flask, render_template, request, abort
from svalid import svalid
from mock import patch

from openc2 import Command, Response, CustomTarget
from stix2 import properties

import itertools
import json
import openc2
import pha
import requests
import uuid

@CustomTarget('x-newcontext-com:aws', [
	('image', properties.StringProperty()),
	('instance', properties.StringProperty()),
])
class NewContextAWS(object):
	pass

CREATE = 'create'
QUERY = 'query'
START = 'start'
STOP = 'stop'
DELETE = 'delete'

app = Flask(__name__)

_instcmds = ('Query', 'Start', 'Stop', 'Delete')

class AWSOpenC2Proxy(object):
	def __init__(self):
		self._pending = {}
		self._ids = {}
		self._baditer = ('badcreate-%d' % i for i in itertools.count(1))

	def pending(self):
		return tuple(self._pending)

	def ec2ids(self):
		return self._ids

	def status(self, inst):
		return self._ids[inst]

	def process_msg(self, cmdid, msg):
		resp = _deseropenc2(msg)

		cmd = self._pending.pop(cmdid)
		if cmd.action == CREATE:
			if resp.status // 100 != 2:
				self._ids[next(self._baditer)] = (
				    resp.status_text)
			else:
				self._ids[resp.results['instance']] = 'marked create'
		elif cmd.action == QUERY:
			self._ids[cmd.target['instance']] = resp.status_text
		elif cmd.action in (START, STOP, DELETE):
			if resp.status // 100 != 2:
				self._ids[cmd.target['instance']] = (
				    resp.status_text)
			else:
				self._ids[cmd.target['instance']] = (
				    'marked %s' % cmd.action)
		else:	# pragma: no cover
			# only can happen when internal state error
			raise RuntimeError

	def _cmdpub(self, action, **kwargs):
		ocpkwargs = {}
		if 'meth' in kwargs:
			ocpkwargs['meth'] = kwargs.pop('meth')

		cmd = Command(action=action, target=NewContextAWS(**kwargs))
		cmduuid = str(uuid.uuid4())

		self._pending[cmduuid] = cmd

		# Do not do any state change after this line.
		# If _publish is sync, a response may come back before
		# we return from this function

		msg = _seropenc2(cmd)
		openc2_publish(cmduuid, msg, **ocpkwargs)

		return cmduuid

	def amicreate(self, ami):
		return self._cmdpub(CREATE, image=ami)

	def ec2query(self, inst):
		return self._cmdpub(QUERY, instance=inst, meth='get')

	def ec2start(self, inst):
		return self._cmdpub(START, instance=inst)

	def ec2stop(self, inst):
		return self._cmdpub(STOP, instance=inst)

	def ec2delete(self, inst):
		return self._cmdpub(DELETE, instance=inst)

	def __contains__(self, item):
		return item in self._pending

for i in (x for x in dir(AWSOpenC2Proxy) if x[0] != '_'):
	# This extra function call seems unneeded, but it is required
	# because i gets late binding, and if we it in the outside, all
	# functions get the same i.  Python doesn't support default named
	# args that are not possition overrideable.  The additional function
	# provides the scope to properly bind i.
	def genfun(i):
		return lambda *args, **kwargs: getattr(get_ec2(), i)(*args,
		    **kwargs)

	locals()[i] = genfun(i)

def get_ec2(obj=[]):
	if not obj:
		app.logger.debug('new proxy')
		obj.append(AWSOpenC2Proxy())

	return obj[0]

def _selfpatch(name):
	return patch('%s.%s' % (__name__, name))

def _seropenc2(msg):
	return msg.serialize()

def _deseropenc2(msg):
	return openc2.parse(msg)

def openc2_publish(cmdid, oc2msg, meth='post'):
	app.logger.debug('publishing msg: %s' % repr(oc2msg))

	resp = getattr(requests, meth)('http://localhost:5001/ec2', data=oc2msg,
	    headers={ 'X-Request-ID': cmdid })
	#import pdb; pdb.set_trace()
	msg = resp.text

	app.logger.debug('response msg: %s' % repr(msg))

	get_ec2().process_msg(resp.headers['X-Request-ID'], msg)

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

_skipSlowTests = False

class FrontendTest(unittest.TestCase):
	def setUp(self):
		self.test_client = app.test_client(self)

	@unittest.skipIf(_skipSlowTests, 'slow')
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

	@unittest.skipIf(_skipSlowTests, 'slow')
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
		cmdid = 'somecmdid'
		retmsg = 'bleh'

		mockpost().text = retmsg
		mockpost().headers = { 'X-Request-ID': cmdid }

		with app.app_context():
			# That when a message is published
			r = openc2_publish(cmdid, msg)

			# it returns the message
			self.assertEqual(r, retmsg)

			# and that it was passed to the actuator
			mockpost.assert_called_with(
			    'http://localhost:5001/ec2', data=msg,
			    headers={ 'X-Request-ID': cmdid })

			# That it was passed on to processing
			mockprocmsg.assert_called_once_with(cmdid, retmsg)

			retmsg = 'othermsg'
			mockget().text = retmsg

			# That when a message is published w/ method get
			r = openc2_publish(cmdid, msg, meth='get')

			# that it returns the correct results
			self.assertEqual(r, retmsg)

			# and that it was passed to the actuator
			mockget.assert_called_with(
			    'http://localhost:5001/ec2', data=msg,
			    headers={ 'X-Request-ID': cmdid })

	def test_badpost(self):
		# That a create request
		response = self.test_client.post('/', data=dict(bad='data',
		    rets='error'))

		# returns an error
		self.assertEqual(response.status_code, 400)

	@unittest.skipIf(_skipSlowTests, 'slow')
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

class ProxyClassTest(unittest.TestCase):
	def test_badcreateiter(self):
		ec2 = get_ec2()

		# that ec2 has a badcreate iter:
		i = ec2._baditer

		# and that it returns expected values)
		self.assertEqual(next(i), 'badcreate-1')
		self.assertEqual(next(i), 'badcreate-2')

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
			oc2p.assert_called_once_with(cmduuid,
			    '{"action": "create", "target": {"x-newcontext-com:aws": {"image": "foo"}}}')

			# and that it's in pending
			self.assertIn(cmduuid, get_ec2())

			# XXX - Test responses later
			#ec2inst = 'instid'

			#resp = Response(source=ec2target, status='OK',
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
				oc2p.assert_called_once_with(cmduuid,
				    '{"action": "%s", "target": {"x-newcontext-com:aws": {"instance": "foo"}}}' % il, **kwargs)

				# and that it's in pending
				self.assertIn(cmduuid, get_ec2())

	@patch('uuid.uuid4')
	@_selfpatch('openc2_publish')
	def test_process_msg(self, oc2p, uuidmock):
		cmduuid = 'auuid'
		uuidmock.return_value = cmduuid

		instid = 'aninstanceid'

		with app.app_context():
			ec2 = get_ec2()

			# That when an AMI is created
			ec2.amicreate('img')

			# and a response is received
			resp = Response(status=200,
			    results=NewContextAWS(instance=instid))
			sresp = _seropenc2(resp)
			ec2.process_msg(cmduuid, sresp)

			# That it's uuid is no longer pending
			self.assertNotIn(cmduuid, ec2.pending())

			# and that the instance is present
			self.assertIn(instid, ec2.ec2ids())

			# and is a dict
			self.assertIsInstance(ec2.ec2ids(), dict)

			# That when an invalid instance is queried
			# it raises an error
			# XXX - not sure this is valid, should we allow
			# unknown instances?
			#self.assertRaises(KeyError, ec2.ec2query,
			#    'bogusinstance')

			# That when the status is requested
			# it returns None at first
			self.assertEqual(ec2.status(instid), 'marked create')

			# but when a valid instance is queried
			ec2.ec2query(instid)

			# and it receives a response
			curstatus = 'pending'
			resp = Response(status=200, status_text=curstatus)
			sresp = _seropenc2(resp)
			ec2.process_msg(cmduuid, sresp)

			# that it returns the status
			self.assertEqual(ec2.status(instid), curstatus)

			# when an instance is started
			ec2.ec2start(instid)

			# and it receives a response
			curstatus = ''
			resp = Response(status=200, status_text=curstatus)
			sresp = _seropenc2(resp)

			# that it works
			ec2.process_msg(cmduuid, sresp)

			# and that the instance is still present
			self.assertIn(instid, ec2.ec2ids())

			# when an instance is stopped
			ec2.ec2stop(instid)

			# and it receives a response
			curstatus = ''
			resp = Response(status=200, status_text=curstatus)
			sresp = _seropenc2(resp)

			# that it works
			ec2.process_msg(cmduuid, sresp)

			# and that the instance is still present
			self.assertIn(instid, ec2.ec2ids())

			with patch.object(ec2, '_baditer') as bi:
				imageid = 'imageid'
				instid = 'badcreate-1'
				bi.__next__.return_value = instid

				# that when a create command fails
				ec2.amicreate(imageid)

				# and it receives a failed response
				curstatus = 'err msg'
				resp = Response(status=400,
				    status_text=curstatus)
				sresp = _seropenc2(resp)

				# that it works
				ec2.process_msg(cmduuid, sresp)

				# and that an instance is created
				self.assertIn(instid, ec2.ec2ids())

				# and has the status report
				self.assertEqual(ec2.status(instid), curstatus)

			# that for each instance command
			for i in _instcmds:
				il = i.lower()

				# when an instance is actioned upon
				getattr(ec2, 'ec2' + il)(instid)

				# and it receives a failed response
				curstatus = 'err msg'
				resp = Response(status=400,
				    status_text=curstatus)
				sresp = _seropenc2(resp)

				# that it works
				ec2.process_msg(cmduuid, sresp)

				# and that the instance is still present
				self.assertIn(instid, ec2.ec2ids())

				# and has the status report
				self.assertEqual(ec2.status(instid), curstatus)
