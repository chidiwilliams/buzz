buzz:
	pyinstaller --noconfirm Buzz.spec

reqs:
	pip3 freeze > requirements.txt
