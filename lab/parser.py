# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://bitbucket.org/ned/coveragepy/src/default/NOTICE.txt

"""Parser.py: a main for invoking code in coverage/parser.py"""

from __future__ import division

import glob, os, sys
import collections
from optparse import OptionParser

import disgen

from coverage.misc import CoverageException
from coverage.parser import ByteParser, PythonParser
from coverage.python import get_python_source

opcode_counts = collections.Counter()


class ParserMain(object):
    """A main for code parsing experiments."""

    def main(self, args):
        """A main function for trying the code from the command line."""

        parser = OptionParser()
        parser.add_option(
            "-c", action="store_true", dest="chunks",
            help="Show basic block chunks"
            )
        parser.add_option(
            "-d", action="store_true", dest="dis",
            help="Disassemble"
            )
        parser.add_option(
            "-H", action="store_true", dest="histogram",
            help="Count occurrences of opcodes"
            )
        parser.add_option(
            "-R", action="store_true", dest="recursive",
            help="Recurse to find source files"
            )
        parser.add_option(
            "-s", action="store_true", dest="source",
            help="Show analyzed source"
            )
        parser.add_option(
            "-t", action="store_true", dest="tokens",
            help="Show tokens"
            )

        options, args = parser.parse_args()
        if options.recursive:
            if args:
                root = args[0]
            else:
                root = "."
            for root, _, _ in os.walk(root):
                for f in glob.glob(root + "/*.py"):
                    self.one_file(options, f)
        elif not args:
            parser.print_help()
        else:
            self.one_file(options, args[0])

        if options.histogram:
            total = sum(opcode_counts.values())
            print("{0} total opcodes".format(total))
            for opcode, number in opcode_counts.most_common():
                print("{0:20s} {1:6d}  {2:.1%}".format(opcode, number, number/total))

    def one_file(self, options, filename):
        """Process just one file."""

        try:
            text = get_python_source(filename)
            bp = ByteParser(text, filename=filename)
        except Exception as err:
            print("%s" % (err,))
            return

        if options.dis:
            print("Main code:")
            self.disassemble(bp, histogram=options.histogram)

        arcs = bp._all_arcs()
        if options.chunks:
            chunks = bp._all_chunks()
            if options.recursive:
                print("%6d: %s" % (len(chunks), filename))
            else:
                print("Chunks: %r" % chunks)
                print("Arcs: %r" % sorted(arcs))

        if options.source or options.tokens:
            cp = PythonParser(filename=filename, exclude=r"no\s*cover")
            cp.show_tokens = options.tokens
            cp.parse_source()

            if options.source:
                arc_width = 0
                arc_chars = {}
                if options.chunks:
                    arc_chars = self.arc_ascii_art(arcs)
                    if arc_chars:
                        arc_width = max(len(a) for a in arc_chars.values())

                exit_counts = cp.exit_counts()

                for lineno, ltext in enumerate(cp.lines, start=1):
                    m0 = m1 = m2 = m3 = a = ' '
                    if lineno in cp.statements:
                        m0 = '='
                    elif lineno in cp.raw_statements:
                        m0 = '-'
                    exits = exit_counts.get(lineno, 0)
                    if exits > 1:
                        m1 = str(exits)
                    if lineno in cp.raw_docstrings:
                        m2 = '"'
                    if lineno in cp.raw_classdefs:
                        m2 = 'C'
                    if lineno in cp.raw_excluded:
                        m3 = 'x'
                    a = arc_chars[lineno].ljust(arc_width)
                    print("%4d %s%s%s%s%s %s" % (lineno, m0, m1, m2, m3, a, ltext))

    def disassemble(self, byte_parser, histogram=False):
        """Disassemble code, for ad-hoc experimenting."""

        for bp in byte_parser.child_parsers():
            chunks = bp._split_into_chunks()
            chunkd = dict((chunk.byte, chunk) for chunk in chunks)
            if bp.text:
                srclines = bp.text.splitlines()
            else:
                srclines = None
            print("\n%s: " % bp.code)
            upto = None
            for disline in disgen.disgen(bp.code):
                if histogram:
                    opcode_counts[disline.opcode] += 1
                    continue
                if disline.first:
                    if srclines:
                        upto = upto or disline.lineno-1
                        while upto <= disline.lineno-1:
                            print("%100s%s" % ("", srclines[upto]))
                            upto += 1
                    elif disline.offset > 0:
                        print("")
                line = disgen.format_dis_line(disline)
                chunk = chunkd.get(disline.offset)
                if chunk:
                    chunkstr = ":: %r" % chunk
                else:
                    chunkstr = ""
                print("%-70s%s" % (line, chunkstr))

        print("")

    def arc_ascii_art(self, arcs):
        """Draw arcs as ascii art.

        Returns a dictionary mapping line numbers to ascii strings to draw for
        that line.

        """

        arc_chars = collections.defaultdict(str)
        for lfrom, lto in sorted(arcs):
            if lfrom < 0:
                arc_chars[lto] += 'v'
            elif lto < 0:
                arc_chars[lfrom] += '^'
            else:
                if lfrom == lto - 1:
                    # Don't show obvious arcs.
                    continue
                if lfrom < lto:
                    l1, l2 = lfrom, lto
                else:
                    l1, l2 = lto, lfrom
                #w = max(len(arc_chars[l]) for l in range(l1, l2+1))
                w = first_all_blanks(arc_chars[l] for l in range(l1, l2+1))
                for l in range(l1, l2+1):
                    if l == lfrom:
                        ch = '<'
                    elif l == lto:
                        ch = '>'
                    else:
                        ch = '|'
                    arc_chars[l] = set_char(arc_chars[l], w, ch)

        return arc_chars


def set_char(s, n, c):
    """Set the nth char of s to be c, extending s if needed."""
    s = s.ljust(n)
    return s[:n] + c + s[n+1:]


def blanks(s):
    """Return the set of positions where s is blank."""
    return set(i for i, c in enumerate(s) if c == " ")


def first_all_blanks(ss):
    """Find the first position that is all blank in the strings ss."""
    ss = list(ss)
    blankss = blanks(ss[0])
    for s in ss[1:]:
        blankss &= blanks(s)
    if blankss:
        return min(blankss)
    else:
        return max(len(s) for s in ss)


if __name__ == '__main__':
    ParserMain().main(sys.argv[1:])
