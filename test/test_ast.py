import unittest
import os
import time

from astex.ast import *

LATEX_TEST = r"""
\newcommand{\test}[1]{Hello, #1!}  % Test command
\test{world}

\upper capitalized
\upper{in-between}lowercase
\nop{}lol"""

TEST_OUTPUT = r"""
\newcommand{\test}[1]{Hello, #1!}  % Test command
\test{world}

Introducing: Capitalized
Introducing: {in-between}lowercase
\nop lol"""


def _remove_empty_brackets(n: Node, _):
    if isinstance(n, BracketNode) and len(n.children) == 0:
        return None

    return n


def _capitalize_next_letter(n: Node, children):
    # Add some text when \upper is encountered
    if isinstance(n, CommandNode) and n.data == 'upper':
        # Capitalize next letter
        temp = read_next(children)
        if isinstance(temp, TextNode):
            temp = TextNode(temp.data.upper())

        temp.parent = n.parent
        children.appendleft(temp)

        # Add some pre-text
        pre = GroupNode()
        pre.take(TextNode("Introducing:"))
        pre.take(WhitespaceNode(' '))
        n.parent.take(pre)

        return None

    return n


class TestAST(unittest.TestCase):
    def test(self):
        def _subtest(n):
            # Test various filter capabilities
            n = n.filter(_capitalize_next_letter)
            n = n.filter(_remove_empty_brackets)
            n = clear_data(fix_whitespace(n))
            self.assertEqual(str(n), TEST_OUTPUT)

        # Text capability
        _subtest(to_ast(text=LATEX_TEST))

        # File capability
        filename = f'test_{int(time.time())}.tex'
        with open(filename, 'w') as f:
            f.write(LATEX_TEST)

        try:
            with open(filename) as f:
                _subtest(to_ast(file=f))

            _subtest(to_ast(file=filename))
        finally:
            os.remove(filename)

