#!/usr/bin/python3
# Check header contents against the given standard.
# Copyright (C) 2018 Free Software Foundation, Inc.
# This file is part of the GNU C Library.
#
# The GNU C Library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# The GNU C Library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with the GNU C Library; if not, see
# <http://www.gnu.org/licenses/>.

import argparse
import fnmatch
import os.path
import re
import subprocess
import sys
import tempfile

import glibcconform


class ElementTest(object):
    """Test for an element of a structure or union type."""

    def __init__(self, dummy, type_name, member_type, member_name, *rest):
        """Initialize an ElementTest object."""
        self.type_name = type_name
        self.member_type = member_type
        self.member_name = member_name
        self.rest = ' '.join(rest)
        self.allow_name = self.member_name

    def run(self, header_tests):
        """Run an ElementTest."""
        text = ('%s a;\n'
                '%s b;\n'
                'extern void xyzzy (__typeof__ (&b.%s), __typeof__ (&a.%s), '
                'unsigned);\n'
                'void foobarbaz (void) {\n'
                'xyzzy (&a.%s, &b.%s, sizeof (a.%s));\n'
                '}\n'
                % (self.type_name, self.type_name,
                   self.member_name, self.member_name,
                   self.member_name, self.member_name, self.member_name))
        header_tests.compile_test('Availability of member %s'
                                  % self.member_name,
                                  text)
        text = ('%s a;\n'
                'extern %s b%s;\n'
                'extern __typeof__ (a.%s) b;\n'
                % (self.type_name, self.member_type, self.rest,
                   self.member_name))
        header_tests.compile_test('Type of member %s' % self.member_name,
                                  text)


class ConstantTest(object):
    """Test for a macro or constant."""

    def __init__(self, symbol_type, symbol, extra1=None, extra2=None,
                 extra3=None):
        """Initialize a ConstantTest object."""
        self.symbol_type = symbol_type
        self.symbol = symbol
        # A comparison operation may be specified without a type.
        if extra2 is not None and extra3 is None:
            self.c_type = None
            self.op = extra1
            self.value = extra2
        else:
            self.c_type = extra1
            self.op = extra2
            self.value = extra3
        self.allow_name = self.symbol

    def run(self, header_tests):
        """Run a ConstantTest."""
        if 'macro' in self.symbol_type:
            text = ('#ifndef %s\n'
                    '# error "Macro %s not defined"\n'
                    '#endif\n'
                    % (self.symbol, self.symbol))
            header_tests.compile_test('Availability of macro %s'
                                      % self.symbol,
                                      text)
        if 'constant' in self.symbol_type:
            text = ('__typeof__ (%s) a = %s;\n'
                    % (self.symbol, self.symbol))
            header_tests.compile_test('Availability of constant %s'
                                      % self.symbol,
                                      text)
        if self.symbol_type == 'macro-int-constant':
            sym_bits_def_neg = ''.join(
                '# if %s & (1LL << %d)\n'
                '#  define conformtest_bit_%d 0LL\n'
                '# else\n'
                '#  define conformtest_bit_%d (1LL << %d)\n'
                '# endif\n'
                % (self.symbol, i, i, i, i) for i in range(63))
            sym_bits_or_neg = '|'.join('conformtest_bit_%d' % i
                                       for i in range(63))
            sym_bits_def_pos = ''.join(
                '# if %s & (1ULL << %d)\n'
                '#  define conformtest_bit_%d (1ULL << %d)\n'
                '# else\n'
                '#  define conformtest_bit_%d 0ULL\n'
                '# endif\n'
                % (self.symbol, i, i, i, i) for i in range(64))
            sym_bits_or_pos = '|'.join('conformtest_bit_%d' % i
                                       for i in range(64))
            text = ('#if %s < 0\n'
                    '# define conformtest_negative 1\n'
                    '%s'
                    '# define conformtest_value ~(%s)\n'
                    '#else\n'
                    '# define conformtest_negative 0\n'
                    '%s'
                    '# define conformtest_value (%s)\n'
                    '#endif\n'
                    '_Static_assert (((%s < 0) == conformtest_negative) '
                    '&& (%s == conformtest_value), '
                    '"value match inside and outside #if");\n'
                    % (self.symbol, sym_bits_def_neg, sym_bits_or_neg,
                       sym_bits_def_pos, sym_bits_or_pos,
                       self.symbol, self.symbol))
            header_tests.compile_test('#if usability of symbol %s'
                                      % self.symbol,
                                      text)
        if self.c_type is not None:
            if self.c_type.startswith('promoted:'):
                c_type = self.c_type[len('promoted:'):]
                text = ('__typeof__ ((%s) 0 + (%s) 0) a;\n'
                        % (c_type, c_type))
            else:
                text = '__typeof__ ((%s) 0) a;\n' % self.c_type
            text += 'extern __typeof__ (%s) a;\n' % self.symbol
            header_tests.compile_test('Type of symbol %s' % self.symbol,
                                      text)
        if self.op is not None:
            text = ('_Static_assert (%s %s %s, "value constraint");\n'
                    % (self.symbol, self.op, self.value))
            header_tests.compile_test('Value of symbol %s' % self.symbol,
                                      text)


class SymbolTest(object):
    """Test for a symbol (not a compile-time constant)."""

    def __init__(self, dummy, symbol, value=None):
        """Initialize a SymbolTest object."""
        self.symbol = symbol
        self.value = value
        self.allow_name = self.symbol

    def run(self, header_tests):
        """Run a SymbolTest."""
        text = ('void foobarbaz (void) {\n'
                '__typeof__ (%s) a = %s;\n'
                '}\n'
                % (self.symbol, self.symbol))
        header_tests.compile_test('Availability of symbol %s'
                                  % self.symbol,
                                  text)
        if self.value is not None:
            text = ('int main (void) { return %s != %s; }\n'
                    % (self.symbol, self.value))
            header_tests.execute_test('Value of symbol %s' % self.symbol,
                                      text)


class TypeTest(object):
    """Test for a type name."""

    def __init__(self, dummy, type_name):
        """Initialize a TypeTest object."""
        self.type_name = type_name
        if type_name.startswith('struct '):
            self.allow_name = type_name[len('struct '):]
            self.maybe_opaque = False
        elif type_name.startswith('union '):
            self.allow_name = type_name[len('union '):]
            self.maybe_opaque = False
        else:
            self.allow_name = type_name
            self.maybe_opaque = True

    def run(self, header_tests):
        """Run a TypeTest."""
        text = ('%s %sa;\n'
                % (self.type_name, '*' if self.maybe_opaque else ''))
        header_tests.compile_test('Availability of type %s' % self.type_name,
                                  text)


class TagTest(object):
    """Test for a tag name."""

    def __init__(self, dummy, type_name):
        """Initialize a TagTest object."""
        self.type_name = type_name
        if type_name.startswith('struct '):
            self.allow_name = type_name[len('struct '):]
        elif type_name.startswith('union '):
            self.allow_name = type_name[len('union '):]
        else:
            raise ValueError('unexpected kind of tag: %s' % type_name)

    def run(self, header_tests):
        """Run a TagTest."""
        # If the tag is not declared, these function prototypes have
        # incompatible types.
        text = ('void foo (%s *);\n'
                'void foo (%s *);\n'
                % (self.type_name, self.type_name))
        header_tests.compile_test('Availability of tag %s' % self.type_name,
                                  text)


class FunctionTest(object):
    """Test for a function."""

    def __init__(self, dummy, return_type, function_name, *args):
        """Initialize a FunctionTest object."""
        self.function_name_full = function_name
        self.args = ' '.join(args)
        if function_name.startswith('(*'):
            # Function returning a pointer to function.
            self.return_type = '%s (*' % return_type
            self.function_name = function_name[len('(*'):]
        else:
            self.return_type = return_type
            self.function_name = function_name
        self.allow_name = self.function_name

    def run(self, header_tests):
        """Run a FunctionTest."""
        text = ('%s (*foobarbaz) %s = %s;\n'
                % (self.return_type, self.args, self.function_name))
        header_tests.compile_test('Availability of function %s'
                                  % self.function_name,
                                  text)
        text = ('extern %s (*foobarbaz) %s;\n'
                'extern __typeof__ (&%s) foobarbaz;\n'
                % (self.return_type, self.args, self.function_name))
        header_tests.compile_test('Type of function %s' % self.function_name,
                                  text)


class VariableTest(object):
    """Test for a variable."""

    def __init__(self, dummy, var_type, var_name, *rest):
        """Initialize a VariableTest object."""
        self.var_type = var_type
        self.var_name = var_name
        self.rest = ' '.join(rest)
        self.allow_name = var_name

    def run(self, header_tests):
        """Run a VariableTest."""
        text = ('typedef %s xyzzy%s;\n'
                'xyzzy *foobarbaz = &%s;\n'
                % (self.var_type, self.rest, self.var_name))
        header_tests.compile_test('Availability of variable %s'
                                  % self.var_name,
                                  text)
        text = ('extern %s %s%s;\n'
                % (self.var_type, self.var_name, self.rest))
        header_tests.compile_test('Type of variable %s' % self.var_name,
                                  text)


class MacroFunctionTest(object):
    """Test for a possibly macro-only function."""

    def __init__(self, dummy, return_type, function_name, *args):
        """Initialize a MacroFunctionTest object."""
        self.return_type = return_type
        self.function_name = function_name
        self.args = ' '.join(args)
        self.allow_name = function_name

    def run(self, header_tests):
        """Run a MacroFunctionTest."""
        text = ('#ifndef %s\n'
                '%s (*foobarbaz) %s = %s;\n'
                '#endif\n'
                % (self.function_name, self.return_type, self.args,
                   self.function_name))
        header_tests.compile_test('Availability of macro %s'
                                  % self.function_name,
                                  text)
        text = ('#ifndef %s\n'
                'extern %s (*foobarbaz) %s;\n'
                'extern __typeof__ (&%s) foobarbaz;\n'
                '#endif\n'
                % (self.function_name, self.return_type, self.args,
                   self.function_name))
        header_tests.compile_test('Type of macro %s' % self.function_name,
                                  text)


class MacroStrTest(object):
    """Test for a string-valued macro."""

    def __init__(self, dummy, macro_name, value):
        """Initialize a MacroStrTest object."""
        self.macro_name = macro_name
        self.value = value
        self.allow_name = macro_name

    def run(self, header_tests):
        """Run a MacroStrTest."""
        text = ('#ifndef %s\n'
                '# error "Macro %s not defined"\n'
                '#endif\n'
                % (self.macro_name, self.macro_name))
        header_tests.compile_test('Availability of macro %s' % self.macro_name,
                                  text)
        # We can't include <string.h> here.
        text = ('extern int (strcmp)(const char *, const char *);\n'
                'int main (void) { return (strcmp) (%s, %s) != 0; }\n'
                % (self.macro_name, self.value))
        header_tests.execute_test('Value of macro %s' % self.macro_name,
                                  text)


class HeaderTests(object):
    """The set of tests run for a header."""

    def __init__(self, header, standard, cc, flags, cross, xfail):
        """Initialize a HeaderTests object."""
        self.header = header
        self.standard = standard
        self.cc = cc
        self.flags = flags
        self.cross = cross
        self.xfail_str = xfail
        self.cflags_namespace = ('%s -fno-builtin %s -D_ISOMAC'
                                 % (flags, glibcconform.CFLAGS[standard]))
        # When compiling the conformance test programs, use of
        # __attribute__ in headers is disabled because of attributes
        # that affect the types of functions as seen by typeof.
        self.cflags = "%s '-D__attribute__(x)='" % self.cflags_namespace
        self.tests = []
        self.allow = set()
        self.allow_fnmatch = set()
        self.headers_handled = set()
        self.total = 0
        self.skipped = 0
        self.errors = 0
        self.xerrors = 0

    def add_allow(self, name, pattern_ok):
        """Add an identifier as an allowed token for this header.

        If pattern_ok, fnmatch patterns are OK as well as
        identifiers.

        """
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            self.allow.add(name)
        elif pattern_ok:
            self.allow_fnmatch.add(name)
        else:
            raise ValueError('bad identifier: %s' % name)

    def check_token(self, bad_tokens, token):
        """Check whether an identifier token is allowed, and record it in
        bad_tokens if not.

        """
        if token.startswith('_'):
            return
        if token in glibcconform.KEYWORDS[self.standard]:
            return
        if token in self.allow:
            return
        for pattern in self.allow_fnmatch:
            if fnmatch.fnmatch(token, pattern):
                return
        bad_tokens.add(token)

    def handle_test_line(self, line, allow):
        """Handle a single line in the test data.

        If allow is true, the header is one specified in allow-header
        and so tests are marked as allowed for namespace purposes but
        otherwise ignored.

        """
        orig_line = line
        xfail = False
        if line.startswith('xfail-'):
            xfail = True
            line = line[len('xfail-'):]
        else:
            match = re.match(r'xfail\[(.*?)\]-(.*)', line)
            if match:
                xfail_cond = match.group(1)
                line = match.group(2)
                # "xfail[cond]-" or "xfail[cond1|cond2|...]-" means a
                # failure of the test is allowed if any of the listed
                # conditions are in the --xfail command-line option
                # argument.
                if self.xfail_str and re.search(r'\b(%s)\b' % xfail_cond,
                                                self.xfail_str):
                    xfail = True
        optional = False
        if line.startswith('optional-'):
            optional = True
            line = line[len('optional-'):]
        # Tokens in test data are space-separated, except for {...}
        # tokens that may contain spaces.
        tokens = []
        while line:
            match = re.match(r'\{(.*?)\}(.*)', line)
            if match:
                tokens.append(match.group(1))
                line = match.group(2)
            else:
                match = re.match(r'([^ ]*)(.*)', line)
                tokens.append(match.group(1))
                line = match.group(2)
            line = line.strip()
        if tokens[0] == 'allow-header':
            if len(tokens) != 2 or xfail or optional:
                raise ValueError('bad allow-header line: %s' % orig_line)
            if tokens[1] not in self.headers_handled:
                self.load_tests(tokens[1], True)
            return
        if tokens[0] == 'allow':
            if len(tokens) != 2 or xfail or optional:
                raise ValueError('bad allow line: %s' % orig_line)
            self.add_allow(tokens[1], True)
            return
        test_classes = {'element': ElementTest,
                        'macro': ConstantTest,
                        'constant': ConstantTest,
                        'macro-constant': ConstantTest,
                        'macro-int-constant': ConstantTest,
                        'symbol': SymbolTest,
                        'type': TypeTest,
                        'tag': TagTest,
                        'function': FunctionTest,
                        'variable': VariableTest,
                        'macro-function': MacroFunctionTest,
                        'macro-str': MacroStrTest}
        test = test_classes[tokens[0]](*tokens)
        test.xfail = xfail
        test.optional = optional
        self.add_allow(test.allow_name, False)
        if not allow:
            self.tests.append(test)

    def load_tests(self, header, allow):
        """Load tests of a header.

        If allow is true, the header is one specified in allow-header
        and so tests are marked as allowed for namespace purposes but
        otherwise ignored.

        """
        self.headers_handled.add(header)
        header_s = header.replace('/', '_')
        temp_file = os.path.join(self.temp_dir, 'header-data-%s' % header_s)
        cmd = ('%s -E -D%s -std=c99 -x c data/%s-data > %s'
               % (self.cc, self.standard, header, temp_file))
        subprocess.check_call(cmd, shell=True)
        with open(temp_file, 'r') as tests:
            for line in tests:
                line = line.strip()
                if line == '' or line.startswith('#'):
                    continue
                self.handle_test_line(line, allow)

    def note_error(self, name, xfail):
        """Note a failing test."""
        if xfail:
            print('XFAIL: %s' % name)
            self.xerrors += 1
        else:
            print('FAIL: %s' % name)
            self.errors += 1
        sys.stdout.flush()

    def note_skip(self, name):
        """Note a skipped test."""
        print('SKIP: %s' % name)
        self.skipped += 1
        sys.stdout.flush()

    def compile_test(self, name, text):
        """Run a compilation test; return True if it passes."""
        self.total += 1
        if self.group_ignore:
            return False
        optional = self.group_optional
        self.group_optional = False
        if self.group_skip:
            self.note_skip(name)
            return False
        c_file = os.path.join(self.temp_dir, 'test.c')
        o_file = os.path.join(self.temp_dir, 'test.o')
        with open(c_file, 'w') as c_file_out:
            c_file_out.write('#include <%s>\n%s' % (self.header, text))
        cmd = ('%s %s -c %s -o %s' % (self.cc, self.cflags, c_file, o_file))
        try:
            subprocess.check_call(cmd, shell=True)
        except subprocess.CalledProcessError:
            if optional:
                print('MISSING: %s' % name)
                sys.stdout.flush()
                self.group_ignore = True
            else:
                self.note_error(name, self.group_xfail)
                self.group_skip = True
            return False
        print('PASS: %s' % name)
        sys.stdout.flush()
        return True

    def execute_test(self, name, text):
        """Run an execution test."""
        self.total += 1
        if self.group_ignore:
            return False
        if self.group_skip:
            self.note_skip(name)
            return
        c_file = os.path.join(self.temp_dir, 'test.c')
        exe_file = os.path.join(self.temp_dir, 'test')
        with open(c_file, 'w') as c_file_out:
            c_file_out.write('#include <%s>\n%s' % (self.header, text))
        cmd = ('%s %s %s -o %s' % (self.cc, self.cflags, c_file, exe_file))
        try:
            subprocess.check_call(cmd, shell=True)
        except subprocess.CalledProcessError:
            self.note_error(name, self.group_xfail)
            return
        if self.cross:
            self.note_skip(name)
            return
        try:
            subprocess.check_call(exe_file, shell=True)
        except subprocess.CalledProcessError:
            self.note_error(name, self.group_xfail)
            return
        print('PASS: %s' % name)
        sys.stdout.flush()

    def check_namespace(self, name):
        """Check the namespace of a header."""
        c_file = os.path.join(self.temp_dir, 'namespace.c')
        out_file = os.path.join(self.temp_dir, 'namespace-out')
        with open(c_file, 'w') as c_file_out:
            c_file_out.write('#include <%s>\n' % self.header)
        cmd = ('%s %s -E %s -P -Wp,-dN > %s'
               % (self.cc, self.cflags_namespace, c_file, out_file))
        subprocess.check_call(cmd, shell=True)
        bad_tokens = set()
        with open(out_file, 'r') as content:
            for line in content:
                line = line.strip()
                if not line:
                    continue
                if re.match(r'# [1-9]', line):
                    continue
                match = re.match(r'#define (.*)', line)
                if match:
                    self.check_token(bad_tokens, match.group(1))
                    continue
                match = re.match(r'#undef (.*)', line)
                if match:
                    bad_tokens.discard(match.group(1))
                    continue
                # Tokenize the line and check identifiers found.  The
                # handling of strings does not allow for escaped
                # quotes, no allowance is made for character
                # constants, and hex floats may be wrongly split into
                # tokens including identifiers, but this is sufficient
                # in practice and matches the old perl script.
                line = re.sub(r'"[^"]*"', '', line)
                line = line.strip()
                for token in re.split(r'[^A-Za-z0-9_]+', line):
                    if re.match(r'[A-Za-z_]', token):
                        self.check_token(bad_tokens, token)
        if bad_tokens:
            for token in sorted(bad_tokens):
                print('    Namespace violation: "%s"' % token)
            self.note_error(name, False)
        else:
            print('PASS: %s' % name)
            sys.stdout.flush()

    def run(self):
        """Load and run tests of a header."""
        with tempfile.TemporaryDirectory() as self.temp_dir:
            self.load_tests(self.header, False)
            self.group_optional = False
            self.group_xfail = False
            self.group_ignore = False
            self.group_skip = False
            available = self.compile_test('Availability of <%s>' % self.header,
                                          '')
            if available:
                for test in self.tests:
                    # A test may run more than one subtest.  If the
                    # initial subtest for an optional symbol fails,
                    # others are not run at all; if the initial
                    # subtest for an optional symbol succeeds, others
                    # are run and are not considered optional; if the
                    # initial subtest for a required symbol fails,
                    # others are skipped.
                    self.group_optional = test.optional
                    self.group_xfail = test.xfail
                    self.group_ignore = False
                    self.group_skip = False
                    test.run(self)
            namespace_name = 'Namespace of <%s>' % self.header
            if available:
                self.check_namespace(namespace_name)
            else:
                self.note_skip(namespace_name)
        print('-' * 76)
        print('  Total number of tests   : %4d' % self.total)
        print('  Number of failed tests  : %4d' % self.errors)
        print('  Number of xfailed tests : %4d' % self.xerrors)
        print('  Number of skipped tests : %4d' % self.skipped)
        sys.exit(1 if self.errors else 0)


def main():
    """The main entry point."""
    parser = argparse.ArgumentParser(description='Check header contents.')
    parser.add_argument('--header', metavar='HEADER',
                        help='name of header')
    parser.add_argument('--standard', metavar='STD',
                        help='standard to use when processing header')
    parser.add_argument('--cc', metavar='CC',
                        help='C compiler to use')
    parser.add_argument('--flags', metavar='CFLAGS',
                        help='Compiler flags to use with CC')
    parser.add_argument('--cross', action='store_true',
                        help='Do not run compiled test programs')
    parser.add_argument('--xfail', metavar='COND',
                        help='Name of condition for XFAILs')
    args = parser.parse_args()
    tests = HeaderTests(args.header, args.standard, args.cc, args.flags,
                        args.cross, args.xfail)
    tests.run()


if __name__ == '__main__':
    main()
