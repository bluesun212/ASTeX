from __future__ import annotations
from typing import Optional, List

from astex.ast import *

__all__ = ["EnvironmentNode", "read_next", "read_bracket_arg", "replace_parameters",
           "fix_whitespace", "clear_data",  "parse_environments"]

from astex.ast import TextNode, GroupNode, CommentNode, Node, ParameterNode


class EnvironmentNode(GroupNode):
    def __init__(self, name=None):
        super().__init__()
        self.name = name

    def __str__(self):
        children_str = super().__str__()
        return f"\\begin{{{self.name}}}{children_str}\\end{{{self.name}}}"

    def copy(self):
        cpy = super().copy()
        cpy.name = self.name
        return cpy


def read_next(n: Node, error=True, skip_whitespace=True, skip_comments=True, should_pop=True) -> Optional[Node]:
    """Get the first non-whitespace, non-comment node in queue, possibly erroring if there was no Node found.
    Only return a single character if a TextNode was found."""
    parent = n.parent
    n = n.next

    while n:
        if not (skip_whitespace and isinstance(n, WhitespaceNode)) and \
                not (skip_comments and isinstance(n, CommentNode)):
            # If it's text, only return a single character
            if isinstance(n, TextNode) and len(n.data) > 1:
                text = n.data
                n = n.replace(TextNode(data=text[0]))
                leftover = TextNode(data=text[1:])
                parent.add(leftover, n)

            return n

        # Throw away this element and get the next
        if should_pop:
            n = n.pop(ret=1)
        else:
            n = n.next

    if error:
        raise ValueError("Unexpected end of tokens")

    return None


def read_bracket_arg(n: Node) -> Optional[GroupNode]:
    temp = read_next(n, error=False)

    if isinstance(temp, TextNode) and temp.data == '[':
        temp.pop()

        # Collect inside elements in new group
        node = GroupNode()

        while True:
            temp = read_next(n, skip_comments=False, skip_whitespace=False)
            if isinstance(temp, TextNode) and temp.data == ']':
                temp.pop()
                break
            node.add(temp)

        # Unwrap if there is only one non-comment element that's a GroupNode
        c = list(filter(lambda x: not isinstance(x, CommentNode), node.children()))
        if len(c) == 1 and isinstance(c[0], GroupNode):
            return c[0]  # type: ignore

        return node

    return None


def replace_parameters(root: GroupNode, parameters: List[Node], copy=True):
    def _do_replace(n):
        if isinstance(n, ParameterNode):
            if n.num_hashes == 1:
                # Replace with parameter value
                obj = parameters[n.param - 1]
                if copy:
                    obj = obj.copy()

                n.parent.take(obj, n, after=False)
                return None
            else:
                n.num_hashes /= 2
                if int(n.num_hashes) != n.num_hashes:
                    raise ValueError("Number of hashes in parameter must be power of 2")

        return n

    return root.filter(_do_replace)


def fix_whitespace(root: GroupNode) -> GroupNode:
    """Inserts a space between alphabetic backslash commands and text if none exists."""

    def _fix_whitespace(n):
        if n.next:
            if isinstance(n, CommandNode) and n.data[0].isalpha() and \
                    isinstance(n.next, TextNode) and n.next.data[0].isalpha():
                n.parent.add(WhitespaceNode(data=' '), n)

        return n

    return root.filter(_fix_whitespace)


def clear_data(root: GroupNode) -> GroupNode:
    """Deletes any extra data stored in the GroupNode objects in the provided Node and its children."""

    def _clear_data(n):
        if isinstance(n, GroupNode):
            n.data = None

        return n

    return root.filter(_clear_data)


def parse_environments(root: GroupNode) -> GroupNode:
    """Filters the given node and replaces matching \\begin and \\end environments with
    an EnvironmentNode, which contains all the in-between nodes, including the environment arguments."""

    def _read_name(n: Node):
        temp = read_next(n)
        name = str(temp)
        if isinstance(temp, BracketNode):
            name = name[1:-1]

        temp.pop()
        return name

    def _parse_environments(n):
        if isinstance(n, CommandNode) and n.data == 'begin':
            # Read in environment name
            env = EnvironmentNode(_read_name(n))
            internal_envs = 0

            # Read until a matching end is encountered
            while internal_envs >= 0:
                temp = n.next
                if isinstance(temp, CommandNode):
                    # This isn't the most efficient when many environments are nested,
                    # but for now this is acceptable
                    if temp.data == 'begin':
                        internal_envs += 1
                    elif temp.data == 'end':
                        internal_envs -= 1
                env.add(temp)

            # Remove the last node because it was the matching \end
            # and check the name to ensure it matches
            env.end.pop()
            if _read_name(n) != env.name:
                raise ValueError("Matching \\end has incorrect environment name")

            return env

        return n

    return root.filter(_parse_environments)
