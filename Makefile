VIRTUALENV ?= virtualenv
VRITUALENVARGS =

FILES=backend.py frontend.py

test:
	(ls $(FILES); find templates -type f) | ~/src/eradman-entr-c15b0be493fc/entr sh -c 'python -m coverage run -m unittest frontend backend && python -m coverage report -m --omit=p/\*'

testmisc:
	echo svalid.py | ~/src/eradman-entr-c15b0be493fc/entr python -m unittest svalid

env:
	($(VIRTUALENV) $(VIRTUALENVARGS) p && . ./p/bin/activate && pip install -r requirements.txt)
