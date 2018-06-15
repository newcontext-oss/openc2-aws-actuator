test:
	(echo frontend.py; find templates -type f) | ~/src/eradman-entr-c15b0be493fc/entr python -m unittest frontend

testmisc:
	echo svalid.py | ~/src/eradman-entr-c15b0be493fc/entr python -m unittest svalid
