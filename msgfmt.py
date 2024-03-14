#!/usr/bin/env python
# Written by Martin v. Lwis <loewis@informatik.hu-berlin.de>
# Plural forms support added by alexander smishlajev <alex@tycobka.lv>
"""
Generate binary message catalog from textual translation description.

This program converts a textual Uniforum-style message catalog (.po file) into
a binary GNU catalog (.mo file).  This is essentially the same function as the
GNU msgfmt program, however, it is a simpler implementation.

Usage: msgfmt.py [OPTIONS] filename.po

Options:
    -o file
    --output-file=file
        Specify the output file to write to.  If omitted, output will go to a
        file named filename.mo (based off the input file name).

    -h
    --help
        Print this message and exit.

    -V
    --version
        Display version information and exit.
"""
import array
import ast
import getopt
import os
import struct
import sys

__version__ = "1.2"

MESSAGES = {}


def usage(ecode, msg=""):
    """
    Print usage and msg and exit with given code.
    """
    print(__doc__, file=sys.stderr)
    if msg:
        print(msg, file=sys.stderr)
    sys.exit(ecode)


def add(msgid, transtr, fuzzy):
    """
    Add a non-fuzzy translation to the dictionary.
    """
    if not fuzzy and transtr and not transtr.startswith("\x00"):
        MESSAGES[msgid] = transtr


def generate():
    """
    Return the generated output.
    """
    # the keys are sorted in the .mo file
    keys = sorted(MESSAGES)
    offsets = []
    ids = strs = ""
    for _id in keys:
        # For each string, we need size and file offset when encoded. Each string is NUL
        # terminated; the NUL does not count into the size.
        offsets.append(
            (
                len(ids.encode("utf8")),
                len(_id.encode("utf8")),
                len(strs.encode("utf8")),
                len(MESSAGES[_id].encode("utf8")),
            )
        )
        ids += _id + "\x00"
        strs += MESSAGES[_id] + "\x00"

    # The header is 7 32-bit unsigned integers.  We don't use hash tables, so
    # the keys start right after the index tables.
    # translated string.
    keystart = 7 * 4 + 16 * len(keys)
    # and the values start after the keys
    valuestart = keystart + len(ids)
    koffsets = []
    voffsets = []
    # The string table first has the list of keys, then the list of values.
    # Each entry has first the size of the string, then the file offset.
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    offsets = koffsets + voffsets
    output = struct.pack(
        "Iiiiiii",
        0x950412DE,  # Magic
        0,  # Version
        len(keys),  # # of entries
        7 * 4,  # start of key index
        7 * 4 + len(keys) * 8,  # start of value index
        0,
        0,
    )  # size and offset of hash table
    output += array.array("i", offsets).tobytes()
    output += ids.encode("utf8")
    output += strs.encode("utf8")
    return output


def make(filename, outfile):
    section_id = 1
    section_str = 2
    global MESSAGES
    MESSAGES = {}

    # Compute .mo name from .po name and arguments
    if filename.endswith(".po"):
        infile = filename
    else:
        infile = filename + ".po"
    if outfile is None:
        outfile = os.path.splitext(infile)[0] + ".mo"

    try:
        with open(infile, encoding="utf8") as _file:
            lines = _file.readlines()
    except OSError as msg:
        print(msg, file=sys.stderr)
        sys.exit(1)

    section = None
    fuzzy = 0

    # Parse the catalog
    msgid = msgstr = ""
    lno = 0
    for line in lines:
        lno += 1
        # If we get a comment line after a msgstr, this is a new entry
        if line[0] == "#" and section == section_str:
            add(msgid, msgstr, fuzzy)
            section = None
            fuzzy = 0
        # Record a fuzzy mark
        if line[:2] == "#," and (line.find("fuzzy") >= 0):
            fuzzy = 1
        # Skip comments
        if line[0] == "#":
            continue
        # Start of msgid_plural section, separate from singular form with \0
        if line.startswith("msgid_plural"):
            msgid += "\x00"
            line = line[12:]
        # Now we are in a msgid section, output previous section
        elif line.startswith("msgid"):
            if section == section_str:
                add(msgid, msgstr, fuzzy)
            section = section_id
            line = line[5:]
            msgid = msgstr = ""
        # Now we are in a msgstr section
        elif line.startswith("msgstr"):
            section = section_str
            line = line[6:]
            # Check for plural forms
            if line.startswith("["):
                # Separate plural forms with \0
                if not line.startswith("[0]"):
                    msgstr += "\x00"
                # Ignore the index - must come in sequence
                line = line[line.index("]") + 1 :]
        # Skip empty lines
        line = line.strip()
        if not line:
            continue
        line = ast.literal_eval(line)
        if section == section_id:
            msgid += line
        elif section == section_str:
            msgstr += line
        else:
            print("Syntax error on %s:%d" % (infile, lno), "before:", file=sys.stderr)
            print(line, file=sys.stderr)
            sys.exit(1)
    # Add last entry
    if section == section_str:
        add(msgid, msgstr, fuzzy)

    # Compute output
    output = generate()

    try:
        with open(outfile, "wb") as _file:
            _file.write(output)
    except OSError as msg:
        print(msg, file=sys.stderr)


def main():
    try:
        opts, args = getopt.getopt(
            sys.argv[1:], "hVo:", ["help", "version", "output-file="]
        )
    except getopt.error as msg:
        usage(1, msg)

    outfile = None
    # parse options
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(0)
        elif opt in ("-V", "--version"):
            print("msgfmt.py", __version__, file=sys.stderr)
            sys.exit(0)
        elif opt in ("-o", "--output-file"):
            outfile = arg
    # do it
    if not args:
        print("No input file given", file=sys.stderr)
        print("Try `msgfmt --help` for more information.", file=sys.stderr)
        return

    for filename in args:
        make(filename, outfile)


if __name__ == "__main__":
    main()
