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
