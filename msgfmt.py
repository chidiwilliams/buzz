#!/usr/bin/env python
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
"""
import getopt
import sys
import polib


def usage(ecode, msg=""):
    """
    Print usage and msg and exit with given code.
    """
    print(__doc__, file=sys.stderr)
    if msg:
        print(msg, file=sys.stderr)
    sys.exit(ecode)


def make(filename, outfile):
    po = polib.pofile(filename)
    po.save_as_mofile(outfile)


def main():
    try:
        opts, args = getopt.getopt(
            sys.argv[1:], "ho:", ["help", "output-file="]
        )
    except getopt.error as msg:
        usage(1, msg)

    outfile = None
    # parse options
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(0)
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
