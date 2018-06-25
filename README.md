# openc2-aws-actuator
PoC Actuator to manage EC2 instances via OpenC2

![Architecture Diagram](https://raw.githubusercontent.com/newcontext-oss/openc2-aws-actuator/master/docs/architecture.diagram.svg?sanitize=true)

# Setup Environment

```
virtualenv-2.7 venv
. ./venv/bin/active
pip install -r requirements.txt
```

Local testing uses Amazon SAM, which is installed via the previous commands.  SAM also requires docker.  Get docker functional.

Getting docker running on MacOSX using MacPorts:
```
sudo port install docker
sudo port install docker-machine
docker-machine create dev
eval $(docker-machine env dev)
```

# Starting

AWS keys must be located in the file `.keys`.  The format is simply:
```
<access_key> <secret_key>
```

That is the access key followed by a space, followed by the secret key.

Starting the daemons:
```
$ FLASK_DEBUG=1 FLASK_APP=frontend.py flask run
$ FLASK_DEBUG=1 FLASK_APP=backend.py flask run -p 5001
```
