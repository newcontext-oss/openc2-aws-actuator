# openc2-aws-actuator
PoC Actuator to manage EC2 instances via OpenC2

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

Running:
```
$ FLASK_DEBUG=1 FLASK_APP=frontend.py flask run
```
