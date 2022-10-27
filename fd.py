import os
import select
import sys
from contextlib import contextmanager
from io import StringIO
from multiprocessing.connection import Connection


@contextmanager
def capture_fd(fd: int):
    """Captures and restores a file descriptor into a pipe

    Args:
        fd (int): file descriptor

    Yields:
        Tuple[int, int]: previous descriptor and pipe output
    """
    pipe_out, pipe_in = os.pipe()
    prev = os.dup(fd)
    os.dup2(pipe_in, fd)
    try:
        yield (prev, pipe_out)
    finally:
        os.dup2(prev, fd)


def more_data(fd: int):
    r, _, _ = select.select([fd], [], [], 0)
    return bool(r)


def read_pipe_str(fd: int):
    out = b''
    while more_data(fd):
        out += os.read(fd, 1024)
    return out.decode('utf-8')


class PipeWriter:
    def __init__(self, pipe: Connection):
        self.pipe = pipe

    def write(self, s: str):
        self.pipe.send(s.strip())


@contextmanager
def pipe_stderr(pipe: Connection):
    sys.stderr = PipeWriter(pipe)

    try:
        yield
    finally:
        sys.stderr = sys.__stderr__


@contextmanager
def pipe_stdout(pipe: Connection):
    sys.stdout = PipeWriter(pipe)

    try:
        yield
    finally:
        sys.stdout = sys.__stdout__
