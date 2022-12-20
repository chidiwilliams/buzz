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
    sys.stderr = ConnWriter(conn)

    try:
        yield
    finally:
        sys.stderr = sys.__stderr__
