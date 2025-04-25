from __future__ import annotations

import re
import copy
from typing import List, Optional, Any


__all__ = ['Node', 'GroupNode', 'TextNode', 'CommandNode', 'CommentNode', 'WhitespaceNode',
           'ParameterNode', 'BracketNode', 'to_ast']

MAX_RECURSE_LEVEL = 256


# Simple tokenizer implementation
class Token:
    def __init__(self, pattern, text, start, end, groups):
        self.pattern = pattern
        self.text = text
        self.start: int = start
        self.end: int = end
        self.groups = groups

    def get_text(self):
        return self.text[self.start:self.end]


class NoMatch(Token):
    def __init__(self, text, start, end):
        super(NoMatch, self).__init__(None, text, start, end, None)


class Tokenizer:
    def __init__(self, patterns):
        self.patterns: List[re.Pattern] = patterns
        self._left_over = ''

    def tokenize(self, text):
        """Tokenize a piece of text by yielding Token objects in order, or a no match token"""

        # Convenience method to update the tokens list at the beginning and once per loop
        def _update_token(pos, start, pattern, t):
            if start >= pos:
                return t  # Keep token if it hasn't been reached
            else:
                m = pattern.search(text, pos)
                if m is None:
                    return None  # No more matches, delete this token from list

                return Token(pattern, text, m.start(), m.end(), m.groups())  # Return new match

        # Get the nearest position of all tokens in string
        tokens = list(filter(None, map(lambda p: _update_token(0, -1, p, None), self.patterns)))
        i = 0

        while tokens and i < len(text):
            # Get the closest match to the current position,
            # yield a no match token if there is no token between the current position and match,
            # then yield the matched token, move forward until end of token, and update token list
            token = min(tokens, key=lambda t: t.start)
            if i < token.start:
                yield NoMatch(text, i, token.start)

            yield token
            i = token.end
            tokens = list(filter(None, map(lambda t: _update_token(i, t.start, t.pattern, t), tokens)))

        # Yield one last no match token if text remains
        if i < len(text):
            yield NoMatch(text, i, len(text))


class Node:
    """Parent class representing a node in the TeX AST."""

    def __init__(self, data=None):
        self.data: Optional[Any] = data
        self.parent: Optional[GroupNode] = None
        self.next: Optional[Node] = None
        self.prev: Optional[Node] = None

    def __str__(self):
        return f"{self.data}"

    def copy(self):
        c = copy.copy(self)
        c.parent = None
        c.next = None
        c.prev = None
        return c

    def pop(self, ret=0):
        n = self
        if ret > 0:
            n = self.next
        elif ret < 0:
            n = self.prev

        if self.parent:
            self.parent.remove(self)
        return n

    def replace(self, new: Node):
        if new is not self:
            self.parent.add(new, self)
            self.parent.remove(self)

        return new


class GroupNode(Node):
    """A Node containing a list of child nodes."""

    def __init__(self):
        super().__init__(None)
        self.start: Optional[Node] = None
        self.end: Optional[Node] = None

    def children(self):
        curr = self.start
        while curr:
            yield curr
            curr = curr.next

    def remove(self, child: Node):
        if child.parent is not self:
            raise ValueError("Called remove on wrong parent")

        # Next and previous nodes
        if child.next is not None:
            child.next.prev = child.prev

        if child.prev is not None:
            child.prev.next = child.next

        # Parent related nodes
        child.parent = None
        if child == self.start:
            self.start = child.next

        if child == self.end:
            self.end = child.prev

        child.next = None
        child.prev = None
        return child

    def add(self, new: Node, child: Optional[Node] = None, after=True):
        if new.parent:
            new.parent.remove(new)
        new.parent = self

        if child is None:
            child = self.end if after else self.start

        if child is None:
            self.start = new
            self.end = new
        elif after:
            if child.next:
                child.next.prev = new
                new.next = child.next
            else:
                self.end = new
            child.next = new
            new.prev = child
        else:
            if child.prev:
                child.prev.next = new
                new.prev = child.prev
            else:
                self.start = new
            child.prev = new
            new.next = child

    def take(self, new: Node, child: Optional[Node] = None, after=True):
        if not isinstance(new, GroupNode):
            self.add(new, child, after)
            return

        if not new.start:
            return

        # Remove all children from parent and get start+end nodes
        start = new.start
        n = start
        new.start = None
        new.end = None

        while True:
            n.parent = self
            if n.next:
                n = n.next
            else:
                end = n
                break

        if child is None:
            child = self.end if after else self.start

        if child is None:
            self.start = start
            self.end = end
            start.prev = None
            end.next = None
        elif after:
            if child.next:
                child.next.prev = end
                end.next = child.next
            else:
                self.end = end
            child.next = start
            start.prev = child
        else:
            if child.prev:
                child.prev.next = start
                start.prev = child.prev
            else:
                self.start = start
            child.prev = end
            end.next = child

    def copy(self):
        """Creates a deep-copy of this node and all of its sub-nodes."""
        new = super().copy()
        new.start = None
        new.end = None

        for c in self.children():
            new.add(c.copy())  # noqa
        return new

    def filter(self, filter_func) -> GroupNode:
        """
        Recursively filter through the AST tree starting at this node, applying the function filter_func.

        :param filter_func: is a function that takes two arguments.  The first is the current node in the
            tree, and the second is the remaining nodes that are queued up.  If the function returns None,
            the current node will be removed, otherwise the returned Node object will be added."""

        def _do_filter(node: GroupNode, level=0):
            if level > MAX_RECURSE_LEVEL:
                raise ValueError("Max recursion level reached")

            # Iterate through the object's children
            n = node.start

            while n:
                # Call the function on the child node, adding the result back if returning a valid object
                n2 = filter_func(n)
                if isinstance(n2, GroupNode):
                    n2 = _do_filter(n2, level + 1)

                if not n2:
                    n = n.pop(1)
                else:
                    n = n.replace(n2).next

            return node

        # Call the function on the root node then go up one node
        obj = filter_func(self)
        return _do_filter(obj)

    def __str__(self):
        return ''.join(map(str, self.children()))


# Tokenizer tokens
TOKEN_COMMENT = re.compile(r"%(.*\n?)", re.MULTILINE)
TOKEN_COMMAND = re.compile(r"\\([a-zA-Z@]{2,}|.)")
TOKEN_PARAMETER = re.compile(r"(#+)(\d)")
TOKEN_LCB = re.compile(r"\{")
TOKEN_RCB = re.compile(r"}")
TOKEN_WHITESPACE = re.compile(r"\s+")
def_tokenizer = Tokenizer([TOKEN_COMMENT, TOKEN_COMMAND, TOKEN_PARAMETER,
                           TOKEN_LCB, TOKEN_RCB, TOKEN_WHITESPACE])


# Latex-specific node types
class TextNode(Node):
    pass


class WhitespaceNode(Node):
    pass


class CommandNode(Node):
    """A node reprenting a slash command."""
    def __str__(self):
        return f"\\{self.data}"


class CommentNode(Node):
    def __str__(self):
        return f"%{self.data}"


class ParameterNode(Node):
    """A node representing a parameter in a macro definition, such as #1 or ####2."""
    def __init__(self, num_hashes, param):
        super().__init__()
        self.num_hashes, self.param = num_hashes, param

    def __str__(self):
        return f"{'#'*self.num_hashes}{self.param}"


class BracketNode(GroupNode):
    def __str__(self):
        children_str = super().__str__()
        return f"{{{children_str}}}"


def to_ast(text: str = None, file=None, tokenizer=None) -> GroupNode:
    """Convert the LaTeX source in text to an AST.  Returns a GroupNode containing the data."""
    # Extract text from file if applicable
    if (file is None) == (text is None):
        raise ValueError("file and text can't both be set or unset!")
    elif file is not None:
        try:
            text = file.read()
        except AttributeError:
            with open(file) as f:
                text = f.read()

    if not tokenizer:
        tokenizer = def_tokenizer

    # Iteratively build up the AST
    root = GroupNode()
    curr = root

    for t in tokenizer.tokenize(text):
        if isinstance(t, NoMatch):
            curr.add(TextNode(t.get_text()))
        elif t.pattern == TOKEN_WHITESPACE:
            curr.add(WhitespaceNode(t.get_text()))
        elif t.pattern == TOKEN_PARAMETER:
            curr.add(ParameterNode(len(t.groups[0]), int(t.groups[1])))
        elif t.pattern == TOKEN_LCB:
            n = BracketNode()
            curr.add(n)
            curr = n
        elif t.pattern == TOKEN_RCB:
            if not isinstance(curr, BracketNode):
                raise ValueError("Number of {s and }s don't match or the order is incorrect")
            curr = curr.parent
        elif t.pattern == TOKEN_COMMENT:
            curr.add(CommentNode(t.groups[0]))
        elif t.pattern == TOKEN_COMMAND:
            curr.add(CommandNode(t.groups[0]))
        else:
            raise ValueError("Invalid token type")

    if curr is not root:
        raise ValueError("Number of {s and }s don't match or the order is incorrect")

    return curr
