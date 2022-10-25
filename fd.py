from contextlib import contextmanager
import os
import select


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
