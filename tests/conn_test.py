import sys
from multiprocessing import Pipe
from unittest.mock import patch

from buzz.conn import ConnWriter, pipe_stderr


def test_pipe_stderr_sends_writes_to_connection():
    recv_conn, send_conn = Pipe(duplex=False)

    with pipe_stderr(send_conn):
        assert isinstance(sys.stderr, ConnWriter)
        sys.stderr.write("50%\n")

    assert recv_conn.recv() == "50%"


def test_pipe_stderr_restores_previous_stderr_not_dunder_stderr():
    # In a windowed Windows build sys.__stderr__ is None while sys.stderr is a
    # no-op stream; restoring __stderr__ would make later writes crash.
    _, send_conn = Pipe(duplex=False)
    previous = sys.stderr

    with patch.object(sys, "__stderr__", None):
        try:
            with pipe_stderr(send_conn):
                raise RuntimeError("whisper-cli failed")
        except RuntimeError:
            pass

    assert sys.stderr is previous
