from __future__ import annotations
from typing import Optional, List

from astex.ast import *

__all__ = ["EnvironmentNode", "read_next", "read_bracket_arg", "replace_parameters",
           "fix_whitespace", "remove_extra_whitespace", "remove_comments", "clear_data", "clean",
           "parse_environments", "get_environment_name"]

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
    # TODO: Safe undo
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


def _fix_whitespace(n):
    if n.next:
        if isinstance(n, CommandNode) and n.data[0].isalpha() and \
                isinstance(n.next, TextNode) and n.next.data[0].isalpha():
            n.parent.add(WhitespaceNode(data=' '), n)

    return n


def _remove_whitespace(node):
    if isinstance(node, WhitespaceNode):
        # Get all subsequent whitespace, find "longest" one
        mode = 0
        n = node

        while isinstance(n, WhitespaceNode):
            if mode < 2:
                newlines = n.data.count('\n')
                if newlines > 1:
                    mode = 2
                elif newlines == 1:
                    mode = 1

            # Remove all whitespace except for the first one
            if n is node:
                n = n.next
            else:
                n = n.pop(1)

        # Simplify whitespace depending on the max length in run
        if mode == 0:
            return WhitespaceNode(' ')
        elif mode == 1:
            return WhitespaceNode('\n')
        else:
            return WhitespaceNode('\n\n')

    return node


def _remove_comments(node: Node):
    return None if isinstance(node, CommentNode) else node


def _clear_data(n):
    if isinstance(n, GroupNode):
        n.data = None

    return n


def fix_whitespace(root: GroupNode) -> GroupNode:
    """Inserts a space between alphabetic backslash commands and text if none exists."""
    return root.filter(_fix_whitespace)


def remove_extra_whitespace(root: GroupNode) -> GroupNode:
    """Simplifies runs of whitespace."""
    return root.filter(_remove_whitespace)


def remove_comments(root: GroupNode):
    """Removes all comments including following whitespace"""
    return root.filter(_remove_comments)


def clear_data(root: GroupNode) -> GroupNode:
    """Deletes any extra data stored in the GroupNode objects in the provided Node and its children."""
    return root.filter(_clear_data)


def clean(root: GroupNode) -> GroupNode:
    """Combines clear_data, remove_comments, remove_extra_whitespace, and fix_whitespace into one function."""

    def _clean(n: Node):
        n = _remove_comments(n)
        if n:
            n = _clear_data(_fix_whitespace(_remove_whitespace(n)))

        return n

    return root.filter(_clean)


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


def get_environment_name(n: Node) -> Optional[str]:
    level = 0

    while n:
        # Find next \begin that isn't followed by matching \end
        if isinstance(n, CommandNode):
            if n.data == 'end':
                level += 1
            elif n.data == 'begin':
                if level == 0:
                    # Read environment name in
                    name_node = read_next(n, should_pop=False)
                    name = str(name_node)
                    if isinstance(name_node, BracketNode):
                        name = name[1:-1]

                    return name

                level -= 1

        # If we reached the beginning of the nodes, check the next level up
        if n.prev:
            n = n.prev
        else:
            if isinstance(n.parent, EnvironmentNode):
                return n.parent.name

            n = n.parent

    return None

