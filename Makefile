test:
	(echo backend.py; echo frontend.py; find templates -type f) | entr-c15b0be493fc/entr sh -c 'python -m coverage run -m unittest frontend backend && python -m coverage report -m --omit=venv/\*'

testmisc:
	echo svalid.py | ~/src/eradman-entr-c15b0be493fc/entr python -m unittest svalid
