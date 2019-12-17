# openc2-aws-actuator
PoC Actuator to manage EC2 instances via OpenC2

![Architecture Diagram](https://raw.githubusercontent.com/newcontext-oss/openc2-aws-actuator/master/docs/architecture.diagram.svg?sanitize=true)

# Setup Environment

Currently only tested w/ Python 3.6.  Should work on most versions of Python 3.

```
make env VIRTUALENV=virtualenv-3.6
. ./p/bin/active
```

# Starting

AWS keys must be located in the file `.keys`.  The format is simply:
```
<access_key> <secret_key>
```

That is the access key followed by a space, followed by the secret key.

Starting the daemons:
```
$ FLASK_DEBUG=1 FLASK_APP=frontend.py flask run &
$ FLASK_DEBUG=1 FLASK_APP=backend.py flask run -p 5001
```

If you want more clear output, run the two commands (the first one w/o the ampersand) in two different terminals.

# Sample HTTP transaction

The below is a sample HTTP trasaction from the front end to the back end.  Note: Carriage returns are not shows for clarity.

The request:
```
GET /ec2 HTTP/1.1
Host: localhost:5001
User-Agent: python-requests/2.22.0
Accept-Encoding: gzip, deflate
Accept: */*
Connection: keep-alive
X-Request-ID: 0f8caf5c-b444-40e8-9247-275fa2856437
Content-Length: 92

{"action": "query", "target": {"x-newcontext-com:aws": {"instance": "i-0acf33de6a9ce5973"}}}
```

The response:
```
HTTP/1.0 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 44
X-Request-ID: 0f8caf5c-b444-40e8-9247-275fa2856437
Server: Werkzeug/0.16.0 Python/3.6.7
Date: Tue, 17 Dec 2019 23:22:18 GMT

{"status": 200, "status_text": "terminated"}
```
