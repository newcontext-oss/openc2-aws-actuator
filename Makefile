test:
	(echo backend.py; echo frontend.py; find templates -type f) | ~/src/eradman-entr-c15b0be493fc/entr python -m unittest frontend backend

testmisc:
	echo svalid.py | ~/src/eradman-entr-c15b0be493fc/entr python -m unittest svalid
