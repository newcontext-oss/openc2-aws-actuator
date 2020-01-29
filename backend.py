from flask import (
	Flask, Response, render_template, request, g, abort, make_response
)
from mock import patch, MagicMock

from openc2 import Command, Response as OpenC2Response

from libcloud.compute.base import NodeImage, NodeSize, Node
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

import itertools
import json
import traceback

from frontend import _seropenc2, _deseropenc2, _instcmds
from frontend import CREATE, START, STOP, DELETE, NewContextAWS

app = Flask(__name__)

import logging
#app.logger.setLevel(logging.DEBUG)

if True:
	# GCE
	provider = Provider.GCE
	gcpkey = '.gcp.json'
	with open(gcpkey) as fp:
		email = json.load(fp)['client_email']
	driverargs = (email, gcpkey)
	driverkwargs = dict(project='openc2-cloud-261123', region='us-west-1')
	createnodekwargs = dict(location='us-central1-a', size='f1-micro')
	# freebsd-12-0-release-amd64
else:
	# EC2
	access_key, secret_key = open('.keys').read().split()
	provider = Provider.EC2
	driverargs = (access_key, secret_key)
	driverkwargs = dict(region='us-west-2')
	sizeobj = MagicMock()
	sizeobj.id = 't2.nano'
	createnodekwargs = dict(size=sizeobj)

def genresp(oc2resp, command_id):
	'''Generate a response from a Response.'''

	# be explicit about encoding, the automatic encoding is undocumented
	body = _seropenc2(oc2resp).encode('utf-8')
	r = Response(response=body, status=oc2resp.status,
	    headers={ 'X-Request-ID': command_id },
	    mimetype='application/openc2-rsp+json;version=1.0')

	return r

class CommandFailure(Exception):
	status_code = 400

	def __init__(self, cmd, msg, command_id, status_code=None):
		self.cmd = cmd
		self.msg = msg
		self.command_id = command_id
		if status_code is not None:
			self.status_code = status_code

@app.errorhandler(CommandFailure)
def handle_commandfailure(err):
	resp = OpenC2Response(status=err.status_code, status_text=err.msg)

	return genresp(resp, err.command_id)

nameiter = ('openc2test-%d' % i for i in itertools.count(1))

@app.route('/', methods=['GET', 'POST'])
@app.route('/ec2', methods=['GET', 'POST'])
def ec2route():
	app.logger.debug('received msg: %s' % repr(request.data))
	try:
		cmdid = request.headers['X-Request-ID']
	except KeyError:
		resp = make_response('missing X-Request-ID header'.encode('us-ascii'), 400)
		resp.charset = 'us-ascii'
		resp.mimetype = 'text/plain'
		return resp

	req = _deseropenc2(request.data)
	ncawsargs = {}
	status = 200
	clddrv = get_clouddriver()
	try:
		if hasattr(req.target, 'instance'):
			inst = req.target.instance
		if request.method == 'POST' and req.action == CREATE:
			ami = req.target['image']
			img = MagicMock()
			img.id = ami
			try:
				inst = req.target.instance
			except AttributeError:
				inst = next(nameiter)
			r = clddrv.create_node(image=img,
			    name=inst, **createnodekwargs)
			inst = r.name
			app.logger.debug('started ami %s, instance id: %s' % (ami, inst))

			res = inst
			ncawsargs['instance'] = inst
		elif request.method == 'POST' and req.action == START:
			get_node(inst).start()

			res = ''
		elif request.method == 'POST' and req.action == STOP:
			if not get_node(inst).stop_node():
				raise RuntimeError(
				    'unable to stop instance: %s' % repr(inst))

			res = ''
		elif request.method == 'POST' and req.action == DELETE:
			get_node(inst).destroy()

			res = ''
		elif request.method in ('GET', 'POST') and req.action == 'query':
			insts = [ x for x in clddrv.list_nodes() if
			    x.name == inst ]

			if insts:
				res = str(insts[0].state)
			else:
				res = 'instance not found'
				status = 404
		else:
			raise Exception('unhandled request')
	except Exception as e:
		app.logger.debug('generic failure: %s' % repr(e))
		app.logger.debug(traceback.format_exc())
		raise CommandFailure(req, repr(e), cmdid)

	if ncawsargs:
		kwargs = dict(results=NewContextAWS(**ncawsargs))
	else:
		kwargs = {}
	resp = OpenC2Response(status=status, status_text=res, **kwargs)

	app.logger.debug('replied msg: %s' % repr(_seropenc2(resp)))

	resp = make_response(_seropenc2(resp))

	# Copy over the command id from the request
	resp.headers['X-Request-ID'] = request.headers['X-Request-ID']

	return resp

def get_node(instname):
	return [ x for x in get_clouddriver().list_nodes() if
	    x.name == instname ][0]

def get_clouddriver():
	if not hasattr(g, 'driver'):
		cls = get_driver(provider)
		g.driver = cls(*driverargs, **driverkwargs)

	return g.driver

import unittest
from libcloud.compute.drivers.dummy import DummyNodeDriver
from libcloud.compute.base import Node
from libcloud.compute.types import NodeState

class BetterDummyNodeDriver(DummyNodeDriver):
	def __init__(self, *args, **kwargs):
		self._numiter = itertools.count(1)

		return super(BetterDummyNodeDriver, self).__init__(*args, **kwargs)

	def create_node(self, **kwargs):
		num = next(self._numiter)

		sizename = kwargs.pop('size', 'defsize')
		name = kwargs.pop('name', 'dummy-%d' % (num))

		n = Node(id=num,
		    name=name,
		    state=NodeState.RUNNING,
		    public_ips=['127.0.0.%d' % (num)],
		    private_ips=[],
		    driver=self,
		    size=NodeSize(id='s1', name=sizename, ram=2048,
		        disk=160, bandwidth=None, price=0.0,
		        driver=self),
		    image=NodeImage(id='i2', name='image', driver=self),
		    extra={'foo': 'bar'})
		self.nl.append(n)
		return n

	def stop_node(self, node):
		node.state = NodeState.STOPPED
		return True

	def start_node(self, node):
		node.state = NodeState.RUNNING
		return True

def _selfpatch(name):
	return patch('%s.%s' % (__name__, name))

class BackendTests(unittest.TestCase):
	def setUp(self):
		self.test_client = app.test_client(self)

	def test_genresp(self):
		res = 'soijef'
		cmdid = 'weoiudf'

		resp = OpenC2Response(status=400)

		# that a generated response
		r = genresp(resp, command_id=cmdid)

		# has the passed in status code
		self.assertEqual(r.status_code, 400)

		# has the correct mime-type
		self.assertEqual(r.content_type, 'application/openc2-rsp+json;version=1.0')

		# has the correct body
		self.assertEqual(r.data, _seropenc2(resp).encode('utf-8'))

		# and the command id in the header
		self.assertEqual(r.headers['X-Request-ID'], cmdid)

		# that a generated response
		resp = OpenC2Response(status=200)
		r = genresp(resp, cmdid)

		# has the passed status code
		self.assertEqual(r.status_code, 200)

	def test_cmdfailure(self):
		cmduuid = 'weoiud'
		ami = 'owiejp'
		failmsg = 'this is a failure message'

		cmd = Command(action=CREATE, target=NewContextAWS(image=ami))

		oc2resp = OpenC2Response(status=500, status_text=failmsg)

		# that a constructed CommandFailure
		failure = CommandFailure(cmd, failmsg, cmduuid, 500)

		# when handled
		r = handle_commandfailure(failure)

		# has the correct status code
		self.assertEqual(r.status_code, 500)

		# has the correct mime-type
		self.assertEqual(r.content_type, 'application/openc2-rsp+json;version=1.0')

		# has the correct body
		self.assertEqual(r.data, _seropenc2(oc2resp).encode('utf-8'))

		# and the command id in the header
		self.assertEqual(r.headers['X-Request-ID'], cmduuid)

		# that a constructed CommandFailure
		failure = CommandFailure(cmd, failmsg, cmduuid, 500)

		# when handled
		r = handle_commandfailure(failure)

		# has the correct status code
		self.assertEqual(r.status_code, 500)

	@_selfpatch('get_driver')
	@_selfpatch('open')
	def test_getclouddriver(self, op, drvmock):
		with app.app_context():
			# That the client object gets returned
			self.assertIs(get_clouddriver(), drvmock()())

			# that the class for the correct provider was obtained
			drvmock.assert_any_call(provider)

			# and that the driver was created with the correct arguments
			drvmock().assert_any_call(*driverargs, **driverkwargs)

			# reset provider class mock
			drvmock().reset_mock()

			# and does no additional calls
			drvmock().assert_not_called()

			# that a second call returns the same object
			self.assertIs(get_clouddriver(), drvmock()())

	def test_nocmdid(self):
		# That a request w/o a command id
		response = self.test_client.post('/ec2', data='bogus')

		# that it fails
		self.assertEqual(response.status_code, 400)

		# that it says why
		self.assertEqual(response.headers['content-type'], 'text/plain; charset=us-ascii')

		# that it says why
		self.assertEqual(response.data, 'missing X-Request-ID header'.encode('utf-8'))

	@_selfpatch('nameiter')
	@_selfpatch('get_clouddriver')
	def test_create(self, drvmock, nameiter):
		cmduuid = 'someuuid'
		ami = 'Ubuntu 9.10'
		instname = 'somename'

		# that the name is return by nameiter
		nameiter.__next__.return_value = instname

		cmd = Command(action=CREATE, target=NewContextAWS(image=ami))

		# Note that 0, creates two nodes, not zero, so create one instead
		dnd = BetterDummyNodeDriver(1)
		dnd.list_nodes()[0].destroy()
		self.assertEqual(len(dnd.list_nodes()), 0)
		drvmock.return_value = dnd

		# That a request to create a command
		response = self.test_client.post('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# that the status is correct
		self.assertEqual(dcmd.status, 200)

		# and that the image was run
		self.assertEqual(len(dnd.list_nodes()), 1)

		# and has the correct instance id
		node = dnd.list_nodes()[0]
		runinstid = node.name
		self.assertEqual(runinstid, instname)
		self.assertEqual(dcmd.results['instance'], runinstid)

		# and was launched w/ the correct size
		self.assertEqual(node.size.name, createnodekwargs['size'])

		# and has the same command id
		self.assertEqual(response.headers['X-Request-ID'], cmduuid)

		# clean up previously launched instance
		dnd.list_nodes()[0].destroy()

		# That a request to create a command w/ instance name
		instname = 'anotherinstancename'
		cmd = Command(action=CREATE, target=NewContextAWS(image=ami,
		    instance=instname))

		response = self.test_client.post('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# that the status is correct
		self.assertEqual(dcmd.status, 200)

		# and that the image was run
		self.assertEqual(len(dnd.list_nodes()), 1)

		# and has the correct instance id
		node = dnd.list_nodes()[0]
		runinstid = node.name
		self.assertEqual(runinstid, instname)
		self.assertEqual(dcmd.results['instance'], runinstid)

		# That when we get the same command as a get request
		response = self.test_client.get('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# that it fails
		self.assertEqual(response.status_code, 400)

	@_selfpatch('get_clouddriver')
	def test_query(self, drvmock):
		cmduuid = 'someuuid'

		dnd = BetterDummyNodeDriver(1)
		drvmock.return_value = dnd

		# Get the existing instance id
		node = dnd.list_nodes()[0]
		instid = node.name

		cmd = Command(action='query', target=NewContextAWS(instance=instid))

		# That a request to query a command
		response = self.test_client.get('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and matches the node state
		self.assertEqual(dcmd.status_text, node.state)

		# and has the same command id
		self.assertEqual(response.headers['X-Request-ID'], cmduuid)

		# that when the instance does not exist
		dnd.list_nodes()[0].destroy()

		# That a request to query a command the returns nothing
		response = self.test_client.get('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and that the status is 404 (instance not found)
		self.assertEqual(dcmd.status, 404)

		# and has the instance id
		self.assertEqual(dcmd.status_text, 'instance not found')

		# That when we post the same command as a get request
		response = self.test_client.post('/ec2',
		    data=_seropenc2(cmd))

		# that it fails
		self.assertEqual(response.status_code, 400)

	@_selfpatch('get_clouddriver')
	def test_start(self, drvmock):
		cmduuid = 'someuuid'

		dnd = BetterDummyNodeDriver(1)
		drvmock.return_value = dnd

		# Get the existing instance id
		instid = dnd.list_nodes()[0].name
		node = dnd.list_nodes()[0]
		node.stop_node()
		self.assertEqual(node.state, NodeState.STOPPED)

		cmd = Command(action=START,
		    target=NewContextAWS(instance=instid))

		# That a request to start an instance
		response = self.test_client.post('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the same command id
		self.assertEqual(response.headers['X-Request-ID'], cmduuid)

		# and that the image was started
		self.assertEqual(node.state, NodeState.RUNNING)

		# That when we get the same command as a get request
		response = self.test_client.get('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# that it fails
		self.assertEqual(response.status_code, 400)

	@_selfpatch('get_clouddriver')
	def test_stop(self, drvmock):
		cmduuid = 'someuuid'

		dnd = BetterDummyNodeDriver(1)
		drvmock.return_value = dnd

		# Get the existing instance id
		instid = dnd.list_nodes()[0].name
		node = dnd.list_nodes()[0]
		self.assertEqual(node.state, NodeState.RUNNING)

		cmd = Command(allow_custom=True, action=STOP,
		    target=NewContextAWS(instance=instid))

		# That a request to stop an instance
		response = self.test_client.post('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the same command id
		self.assertEqual(response.headers['X-Request-ID'], cmduuid)

		# and that the image was stopped
		self.assertEqual(node.state, NodeState.STOPPED)

		# That when we get the same command as a get request
		response = self.test_client.get('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# that it fails
		self.assertEqual(response.status_code, 400)

		with patch.object(dnd, 'stop_node') as sn:
			# that when a stop command
			cmd = Command(action=STOP,
			    target=NewContextAWS(instance=instid))

			# and it returns an error
			sn.return_value = False

			# That a request to stop an instance
			response = self.test_client.post('/ec2', data=_seropenc2(cmd),
			    headers={ 'X-Request-ID': cmduuid })

			# fails
			self.assertEqual(response.status_code, 400)

			# that it has a Response body
			resp = _deseropenc2(response.data)

			# that it is an ERR
			self.assertEqual(resp.status, 400)

			# that it references the correct command
			self.assertEqual(response.headers['X-Request-ID'], cmduuid)

	@_selfpatch('get_clouddriver')
	def test_delete(self, drvmock):
		#terminate_instances
		cmduuid = 'someuuid'

		dnd = BetterDummyNodeDriver(1)
		drvmock.return_value = dnd

		# Get the existing instance id
		instid = dnd.list_nodes()[0].name
		node = dnd.list_nodes()[0]

		cmd = Command(action=DELETE,
		    target=NewContextAWS(instance=instid))

		# That a request to create a command
		response = self.test_client.post('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the same command id
		self.assertEqual(response.headers['X-Request-ID'], cmduuid)

		# and that the image was terminated
		self.assertEqual(node.state, NodeState.TERMINATED)

		# That when we get the same command as a get request
		response = self.test_client.get('/ec2', data=_seropenc2(cmd),
		    headers={ 'X-Request-ID': cmduuid })

		# that it fails
		self.assertEqual(response.status_code, 400)
