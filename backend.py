from flask import Flask, Response, render_template, request, g, abort
from mock import patch

import lycan.datamodels as openc2
from lycan.message import OpenC2Command, OpenC2Response
from lycan.serializations import OpenC2MessageEncoder

import boto3
import botocore.exceptions
import json
import traceback

from frontend import _seropenc2, _deseropenc2, ec2target, _instcmds
from frontend import CREATE, START, STOP, DELETE

app = Flask(__name__)

def genresp(oc2resp, status_code=200):
	'''Generate a response from a OpenC2Response.'''

	body = _seropenc2(oc2resp)
	r = Response(response=body, status=status_code, mimetype='application/json')

	return r

class CommandFailure(Exception):
	status_code = 400

	def __init__(self, cmd, msg, status_code=None):
		self.cmd = cmd
		self.msg = msg
		if status_code is not None:
			self.status_code = status_code

@app.errorhandler(CommandFailure)
def handle_commandfailure(err):
	#import pdb; pdb.set_trace()
	resp = OpenC2Response(source=ec2target, status='ERR',
	    results=err.msg, cmdref=err.cmd.modifiers['command_id'])

	return genresp(resp, err.status_code)

@app.route('/ec2', methods=['GET', 'POST'])
def ec2route():
	app.logger.debug('received msg: %s' % `request.data`)
	req = _deseropenc2(request.data)
	try:
		if request.method == 'POST' and req.action == CREATE:
			ami = req.modifiers['image']
			r = get_bec2().run_instances(ImageId=ami,
			    MinCount=1, MaxCount=1)

			inst = r['Instances'][0]['InstanceId']
			app.logger.debug('started ami %s, instance id: %s' % (ami, inst))

			res = inst
		elif request.method == 'POST' and req.action == START:
			r = get_bec2().start_instances(InstanceIds=[
			    req.modifiers['instance'] ])

			res = ''
		elif request.method == 'POST' and req.action == STOP:
			r = get_bec2().stop_instances(InstanceIds=[
			    req.modifiers['instance'] ])

			res = ''
		elif request.method == 'POST' and req.action == DELETE:
			r = get_bec2().terminate_instances(InstanceIds=[
			    req.modifiers['instance'] ])

			res = ''
		elif request.method == 'GET' and req.action == 'query':
			r = get_bec2().describe_instances(InstanceIds=[
			    req.modifiers['instance'] ])

			insts = r['Reservations']
			if insts:
				res = insts[0]['Instances'][0]['State']['Name']
			else:
				res = 'instance not found'
		else:
			raise Exception('unhandled request')
	except botocore.exceptions.ClientError as e:
		app.logger.debug('operation failed: %s' % `e`)
		raise CommandFailure(req, `e`)
	except Exception as e:
		app.logger.debug('generic failure: %s' % `e`)
		app.logger.debug(traceback.format_exc())
		raise CommandFailure(req, `e`)

	resp = OpenC2Response(source=ec2target, status='OK',
	    results=res, cmdref=req.modifiers['command_id'])

	return _seropenc2(resp)

def get_bec2():
	if not hasattr(g, 'bec2'):
		access_key, secret_key = open('.keys').read().split()
		g.bec2 = boto3.client('ec2', region_name='us-west-2', aws_access_key_id=access_key, aws_secret_access_key=secret_key)

	return g.bec2

import unittest

def _selfpatch(name):
	return patch('%s.%s' % (__name__, name))

class BackendTests(unittest.TestCase):
	def setUp(self):
		self.test_client = app.test_client(self)

	def test_genresp(self):
		res = 'soijef'
		cmdid = 'weoiudf'
		resp = OpenC2Response(source=ec2target, status='OK',
		    results=res, cmdref=cmdid)

		# that a generated response
		r = genresp(resp, 400)

		# has the passed in status code
		self.assertEqual(r.status_code, 400)

		# has the correct mime-type
		self.assertEqual(r.mimetype, 'application/json')

		# has the correct body
		self.assertEqual(r.data, _seropenc2(resp))

		# that a generated response
		r = genresp(resp)

		# has the default status code
		self.assertEqual(r.status_code, 200)

	def test_cmdfailure(self):
		cmduuid = 'weoiud'
		ami = 'owiejp'
		failmsg = 'this is a failure message'

		cmd = OpenC2Command(action=CREATE, target=ec2target,
		    modifiers={ 'image': ami, 'command_id': cmduuid })

		oc2resp = OpenC2Response(source=ec2target, status='ERR',
		    results=failmsg, cmdref=cmd.modifiers['command_id'])

		# that a constructed CommandFailure
		failure = CommandFailure(cmd, failmsg)

		# when handled
		r = handle_commandfailure(failure)

		# has the correct status code
		self.assertEqual(r.status_code, 400)

		# has the correct mime-type
		self.assertEqual(r.mimetype, 'application/json')

		# has the correct body
		self.assertEqual(r.data, _seropenc2(oc2resp))

		# that a constructed CommandFailure
		failure = CommandFailure(cmd, failmsg, 500)

		# when handled
		r = handle_commandfailure(failure)

		# has the correct status code
		self.assertEqual(r.status_code, 500)

	@patch('boto3.client')
	@_selfpatch('open')
	def test_getbec2(self, op, b3cl):
		acckey = 'abc'
		seckey = '123'

		robj = object()
		op().read.return_value = '%s %s' % (acckey, seckey)
		boto3.client.return_value = robj

		with app.app_context():
			# That the client object gets returned
			self.assertIs(get_bec2(), robj)

			# and that the correct file was opened
			op.assert_called_with('.keys')

			# and that the client was created with the correct arguments
			b3cl.assert_called_once_with('ec2',
			    region_name='us-west-2', aws_access_key_id=acckey,
			    aws_secret_access_key=seckey)

	@_selfpatch('get_bec2')
	def test_create(self, bec2):
		cmduuid = 'someuuid'
		instid = 'sdkj'
		ami = 'bogusimage'

		cmd = OpenC2Command(action=CREATE, target=ec2target,
		    modifiers={ 'image': ami, 'command_id': cmduuid })

		bec2().run_instances.return_value = {
			'Instances': [ {
					'InstanceId': instid,
				     } ]
		}

		# That a request to create a command
		response = self.test_client.post('/ec2', data=_seropenc2(cmd))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# that the status is correct
		self.assertEqual(dcmd.status, 'OK')

		# and has the instance id
		self.assertEqual(dcmd.results, instid)

		# and has the same command id
		self.assertEqual(dcmd.cmdref, cmduuid)

		# and that the image was run
		bec2().run_instances.assert_called_once_with(ImageId=ami,
		    MinCount=1, MaxCount=1)

		# That when we get the same command as a get request
		response = self.test_client.get('/ec2', data=_seropenc2(cmd))

		# that it fails
		self.assertEqual(response.status_code, 400)

	@_selfpatch('get_bec2')
	def test_query(self, bec2):
		cmduuid = 'someuuid'
		instid = 'sdkj'

		cmd = OpenC2Command(action='query', target=ec2target,
		    modifiers={ 'instance': instid, 'command_id': cmduuid })

		inststate = 'pending'
		instdesc = {
			'InstanceId': instid,
			'some': 'other',
			'data': 'included',
			'State': {
				'Code': 38732,
				'Name': 'pending',
			}
		}
		bec2().describe_instances.return_value = {
			'Reservations': [ {
				'Instances': [ instdesc ],
			} ]
		}

		# That a request to query a command
		response = self.test_client.get('/ec2', data=_seropenc2(cmd))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the instance id
		self.assertEqual(dcmd.results, inststate)

		# and has the same command id
		self.assertEqual(dcmd.cmdref, cmduuid)

		# and that the image was run
		bec2().describe_instances.assert_called_once_with(InstanceIds=[ instid ])

		bec2().describe_instances.return_value = {
			'Reservations': [],
		}

		# That a request to query a command the returns nothing
		response = self.test_client.get('/ec2', data=_seropenc2(cmd))

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the instance id
		self.assertEqual(dcmd.results, 'instance not found')

		# That when we post the same command as a get request
		response = self.test_client.post('/ec2',
		    data=_seropenc2(cmd))

		# that it fails
		self.assertEqual(response.status_code, 400)

	@_selfpatch('get_bec2')
	def test_start(self, bec2):
		cmduuid = 'someuuid'
		instid = 'sdkj'

		cmd = OpenC2Command(action=START, target=ec2target,
		    modifiers={ 'instance': instid, 'command_id': cmduuid })

		bec2().start_instances.return_value = {
			'StartingInstances': [ {
					'InstanceId': instid,
				     } ]
		}

		# That a request to start an instance
		response = self.test_client.post('/ec2', data=_seropenc2(cmd))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the same command id
		self.assertEqual(dcmd.cmdref, cmduuid)

		# and that the image was started
		bec2().start_instances.assert_called_once_with(InstanceIds=[ instid ])

		# That when we get the same command as a get request
		response = self.test_client.get('/ec2', data=_seropenc2(cmd))

		# that it fails
		self.assertEqual(response.status_code, 400)

	@_selfpatch('get_bec2')
	def test_stop(self, bec2):
		cmduuid = 'someuuid'
		instid = 'sdkj'

		cmd = OpenC2Command(action=STOP, target=ec2target,
		    modifiers={ 'instance': instid, 'command_id': cmduuid })

		bec2().stop_instances.return_value = {
			'StoppingInstances': [ {
					'InstanceId': instid,
				     } ]
		}

		# That a request to stop an instance
		response = self.test_client.post('/ec2', data=_seropenc2(cmd))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the same command id
		self.assertEqual(dcmd.cmdref, cmduuid)

		# and that the image was stopped
		bec2().stop_instances.assert_called_once_with(InstanceIds=[ instid ])

		# That when we get the same command as a get request
		response = self.test_client.get('/ec2', data=_seropenc2(cmd))

		# that it fails
		self.assertEqual(response.status_code, 400)

		# that when a stop command
		cmd = OpenC2Command(action=STOP, target=ec2target,
		    modifiers={ 'instance': instid, 'command_id': cmduuid })

		# and AWS returns an error
		bec2().stop_instances.side_effect = \
		    botocore.exceptions.ClientError({}, 'stop_instances')

		# That a request to stop an instance
		response = self.test_client.post('/ec2', data=_seropenc2(cmd))

		# fails
		self.assertEqual(response.status_code, 400)

		# that it has a OpenC2Response body
		resp = _deseropenc2(response.data)

		# that it is an ERR
		self.assertEqual(resp.status, 'ERR')

		# that it references the correct command
		self.assertEqual(resp.cmdref, cmduuid)

	@_selfpatch('get_bec2')
	def test_delete(self, bec2):
		#terminate_instances
		cmduuid = 'someuuid'
		instid = 'sdkj'

		cmd = OpenC2Command(action=DELETE, target=ec2target,
		    modifiers={ 'instance': instid, 'command_id': cmduuid })

		bec2().terminate_instances.return_value = {
			'TerminatingInstances': [ {
					'InstanceId': instid,
				     } ]
		}

		# That a request to create a command
		response = self.test_client.post('/ec2', data=_seropenc2(cmd))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the same command id
		self.assertEqual(dcmd.cmdref, cmduuid)

		# and that the image was terminated
		bec2().terminate_instances.assert_called_once_with(InstanceIds=[ instid ])

		# That when we get the same command as a get request
		response = self.test_client.get('/ec2', data=_seropenc2(cmd))

		# that it fails
		self.assertEqual(response.status_code, 400)
