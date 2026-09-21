#!/usr/bin/env python3
"""Clear the executable-stack flag from bundled ELF shared objects.

uv's python-build-standalone ships libpython marked PT_GNU_STACK = RWE, and
PyInstaller copies it verbatim. Recent kernels (Ubuntu 26.04 / Linux 7.0)
refuse to make the stack executable at dlopen time, so loading the library
dies with:

    cannot enable executable stack as shared object requires: Invalid argument

Nothing in CPython actually needs an executable stack -- the flag is a build
artifact -- so clearing PF_X on the PT_GNU_STACK header is the accepted fix.
This is the same edit `execstack -c` / `patchelf --clear-execstack` perform,
done here so the build needs no extra tooling.
"""

import os
import struct
import sys

PT_GNU_STACK = 0x6474E551
PF_X = 0x1


def clear_execstack(path):
    """Return True if the file was modified."""
    with open(path, "rb") as fh:
        header = fh.read(64)

    # ELF64, little-endian only -- the only shape we ship on Linux.
    if len(header) < 64 or header[:4] != b"\x7fELF":
        return False
    if header[4] != 2 or header[5] != 1:
        return False

    e_phoff = struct.unpack_from("<Q", header, 0x20)[0]
    e_phentsize = struct.unpack_from("<H", header, 0x36)[0]
    e_phnum = struct.unpack_from("<H", header, 0x38)[0]
    if not e_phoff or e_phentsize < 8:
        return False

    with open(path, "r+b") as fh:
        for i in range(e_phnum):
            entry = e_phoff + i * e_phentsize
            fh.seek(entry)
            chunk = fh.read(8)
            if len(chunk) < 8:
                break
            p_type, p_flags = struct.unpack("<II", chunk)
            if p_type != PT_GNU_STACK or not (p_flags & PF_X):
                continue
            fh.seek(entry + 4)
            fh.write(struct.pack("<I", p_flags & ~PF_X))
            return True
    return False


def main(argv):
    if len(argv) < 2:
        print("usage: clear-execstack.py <dir-or-file>...", file=sys.stderr)
        return 2

    targets = []
    for arg in argv[1:]:
        if os.path.isdir(arg):
            for root, _dirs, files in os.walk(arg):
                targets.extend(os.path.join(root, f) for f in files)
        else:
            targets.append(arg)

    patched = 0
    for target in targets:
        if os.path.islink(target) or not os.path.isfile(target):
            continue
        try:
            if clear_execstack(target):
                print(f"    cleared execstack: {target}")
                patched += 1
        except OSError as exc:
            print(f"    warning: {target}: {exc}", file=sys.stderr)

    print(f"    {patched} file(s) patched")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
