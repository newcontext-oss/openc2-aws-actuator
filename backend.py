from flask import Flask, render_template, request, g, abort
from mock import patch

import lycan.datamodels as openc2
from lycan.message import OpenC2Command, OpenC2Response
from lycan.serializations import OpenC2MessageEncoder

import boto3
import json

from frontend import _seropenc2, _deseropenc2, CREATE, ec2target, _instcmds

app = Flask(__name__)

@app.route('/ec2', methods=['GET', 'POST'])
def ec2route():
	req = _deseropenc2(request.data)
	if request.method == 'POST' and req.action == 'create':
		r = get_bec2().run_instances(ImageId=req.modifiers['image'],
		    MinCount=1, MaxCount=1)

		resp = OpenC2Response(source=ec2target, status='OK',
		    results=r['Instances'][0]['InstanceId'],
		    cmdref=req.modifiers['command_id'])
	elif request.method == 'GET' and req.action == 'query':
		r = get_bec2().describe_instances(InstanceIds=[
		    req.modifiers['instance'] ])

		res = json.dumps(r['Reservations'][0]['Instances'][0])
		resp = OpenC2Response(source=ec2target, status='OK',
		    results=res,
		    cmdref=req.modifiers['command_id'])
	else:
		abort(400)

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

		# XXX - correct?
		instdesc = {
			'InstanceId': instid,
			'some': 'other',
			'data': 'included',
		}
		bec2().describe_instances.return_value = {
			'Reservations': [ {
				'Instances': [ instdesc ],
			} ]
		}

		# That a request to create a command
		response = self.test_client.get('/ec2', data=_seropenc2(cmd))

		# Is successful
		self.assertEqual(response.status_code, 200)

		# and returns a valid OpenC2 response
		dcmd = _deseropenc2(response.data)

		# and has the instance id
		self.assertEqual(json.loads(dcmd.results), instdesc)

		# and has the same command id
		self.assertEqual(dcmd.cmdref, cmduuid)

		# and that the image was run
		bec2().describe_instances.assert_called_once_with(InstanceIds=[ instid ])

		# That when we post the same command as a get request
		response = self.test_client.post('/ec2',
		    data=_seropenc2(cmd))

		# that it fails
		self.assertEqual(response.status_code, 400)
