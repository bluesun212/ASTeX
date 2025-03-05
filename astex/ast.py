import re
import copy
from typing import List, Optional, Any
from collections import deque


__all__ = ['Node', 'GroupNode', 'TextNode', 'CommandNode', 'CommentNode', 'WhitespaceNode',
           'ParameterNode', 'BracketNode', 'to_ast', 'fix_whitespace', 'clear_data', 'read_next']

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

    def __str__(self):
        return f"{self.data}"

    def copy(self):
        return copy.copy(self)


class GroupNode(Node):
    """A Node containing a list of child nodes."""

    def __init__(self):
        super().__init__(None)
        self.children: List[Node] = []

    def add(self, child):
        """Adds a child node to this node."""
        self.children.append(child)
        child.parent = self

    def copy(self):
        """Creates a deep-copy of this node and all of its sub-nodes."""
        new = self.__class__()
        for c in self.children:
            new.add(c.copy())
        return new

    def take(self, node):
        """If node is a GroupNode, then take all of its child nodes.  Otherwise, add node as a child."""

        if isinstance(node, GroupNode):
            for c in node.children:
                self.add(c)
        else:
            self.add(node)

    def filter(self, filter_func, should_copy=True):
        """
        Recursively filter through the AST tree starting at this node, applying the function filter_func.

        :param filter_func: is a function that takes two arguments.  The first is the current node in the
        tree, and the second is the remaining nodes that are queued up.  If the function returns None,
        the current node will be removed, otherwise the returned Node object will be added.
        :param should_copy: determines whether the tree will first be copied, and defaults to true."""

        def _do_filter(node, level=0):
            if level > MAX_RECURSE_LEVEL:
                raise ValueError("Max recursion level reached")

            # Iterate through the object's children using a queue
            children = deque(node.children)
            node.children = []

            while children:
                n = children.popleft()

                # Call the function on the child node, adding the result back if returning a valid object
                n = filter_func(n, children)
                if isinstance(n, GroupNode):
                    n = _do_filter(n, level + 1)
                if n:
                    node.add(n)

            return node

        # Call the function on the root node, copying if required, then go up one node
        obj = filter_func(self.copy() if should_copy else self, deque())
        return _do_filter(obj)

    def __str__(self):
        return ''.join(map(str, self.children))


# Tokenizer tokens
TOKEN_COMMENT = re.compile(r"%(.*\n?)", re.MULTILINE)
TOKEN_COMMAND = re.compile(r"\\([a-zA-Z@]{2,}|.)")
TOKEN_PARAMETER = re.compile(r"(#+)(\d)")
TOKEN_LCB = re.compile(r"(?<!\\)\{")
TOKEN_RCB = re.compile(r"(?<!\\)}")
TOKEN_WHITESPACE = re.compile(r"(?<!\\)\s+")
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


def to_ast(text: str = None, file=None, tokenizer=None):
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
    curr = GroupNode()
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

    return curr


def fix_whitespace(root: GroupNode):
    """Inserts a space between alphabetic backslash commands and text if none exists."""

    def _fix_whitespace(n, children: deque):
        if children:
            if isinstance(n, CommandNode) and n.data[0].isalpha():
                if isinstance(children[0], TextNode) and children[0].data[0].isalpha():
                    padding = WhitespaceNode(data=' ')
                    padding.parent = n.parent
                    children.appendleft(padding)

        return n

    return root.filter(_fix_whitespace)


def clear_data(root):
    """Deletes any extra data stored in the GroupNode objects in the provided Node and its children."""

    def _clear_data(n, _):
        if isinstance(n, GroupNode):
            n.data = None

        return n

    return root.filter(_clear_data, False)


def read_next(it: deque, error=True) -> Optional[Node]:
    """Get the first non-whitespace, non-comment node in queue, possibly erroring if there was no Node found.
    Only return a single character if a TextNode was found."""
    try:
        while True:
            n = it.popleft()
            if not (isinstance(n, WhitespaceNode) or isinstance(n, CommentNode)):
                # If it's text, only return a single character
                if isinstance(n, TextNode) and len(n.data) > 1:
                    leftover = TextNode(data=n.data[1:])
                    leftover.parent = n.parent
                    it.appendleft(leftover)
                    n = TextNode(data=n.data[0])

                return n
    except IndexError:
        if error:
            raise ValueError("Unexpected end of tokens")

    return None
