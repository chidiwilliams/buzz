import sys
from contextlib import contextmanager
from multiprocessing.connection import Connection


class ConnWriter:
    def __init__(self, conn: Connection):
        self.conn = conn

    def write(self, s: str):
        self.conn.send(s.strip())


@contextmanager
def pipe_stderr(conn: Connection):
    # Restore the previous stream, not sys.__stderr__: in a windowed Windows
    # build sys.__stderr__ is None, and multiprocessing then crashes writing
    # the child's traceback.
    previous_stderr = sys.stderr
    sys.stderr = ConnWriter(conn)

    try:
        yield
    finally:
        sys.stderr = previous_stderr
