# openc2-aws-actuator
PoC Actuator to manage EC2 instances via OpenC2

![Architecture Diagram](https://raw.githubusercontent.com/newcontext-oss/openc2-aws-actuator/master/docs/architecture.diagram.svg?sanitize=true)

# Setup Environment

Currently only functions and tested w/ Python 2.7.

```
virtualenv-2.7 venv
. ./venv/bin/active
pip install -r requirements.txt
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
