all: linter tests

linter:
	flake8 demucs
	mypy demucs

tests: test_train test_eval

test_train: tests/musdb
	_DORA_TEST_PATH=/tmp/demucs python3 -m dora run --clear \
		dset.musdb=./tests/musdb dset.segment=4 dset.shift=2 epochs=2 model=demucs \
		demucs.depth=2 demucs.channels=4 test.sdr=false misc.num_workers=0 test.workers=0 \
		test.shifts=0

test_eval:
	python3 -m demucs -n demucs_unittest test.mp3
	python3 -m demucs -n demucs_unittest --two-stems=vocals test.mp3
	python3 -m demucs -n demucs_unittest --mp3 test.mp3
	python3 -m demucs -n demucs_unittest --flac --int24 test.mp3
	python3 -m demucs -n demucs_unittest --int24 --clip-mode clamp test.mp3
	python3 -m demucs -n demucs_unittest --segment 8 test.mp3
	python3 -m demucs.api -n demucs_unittest --segment 8 test.mp3
	python3 -m demucs --list-models

tests/musdb:
	test -e tests || mkdir tests
	python3 -c 'import musdb; musdb.DB("tests/tmp", download=True)'
	musdbconvert tests/tmp tests/musdb

dist:
	python3 setup.py sdist

clean:
	rm -r dist build *.egg-info

.PHONY: linter dist test_train test_eval
