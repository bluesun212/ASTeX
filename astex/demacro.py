# Future ideas:
# - option to strip comments
# - option to expand \include or look into \usepackage for macros
# - Handling \def, \let, etc
# - Dealing with paragraph breaks in commands


from .ast import *
from collections import deque
from inspect import signature

__all__ = ['Demacro']


# Demacro static methods
def _filter_children(node, filter_ws=True):
    if isinstance(node, GroupNode):
        c = list(filter(lambda n: not isinstance(n, CommentNode) and
                 (not isinstance(n, WhitespaceNode) or not filter_ws), node.children))
        if len(c) == 1:
            return c[0]

    return None


def _read_until_end_bracket(it: deque):
    node = GroupNode()

    while True:
        n = read_next(it)
        if isinstance(n, TextNode) and n.data == ']':
            break
        node.add(n)

    return node


# Newcommand-related ones
# FIXME: I know this isn't exactly how LaTeX implements these 2 commands, but this is good enough
def _read_command_name(it):
    # Ignore stars for now, TODO
    n = read_next(it)
    if isinstance(n, TextNode) and n.data == '*':
        n = read_next(it)

    # Extract command name
    n = _filter_children(n) or n
    if isinstance(n, CommandNode):
        return n.data

    raise ValueError("Incorrectly formatted command name")


def _extract_arguments(node):
    # Read the number of arguments and convert to a number
    node = _filter_children(node) or node
    if isinstance(node, TextNode):
        try:
            args = int(node.data)
            if 0 <= args < 10:
                return args
        except ValueError:
            pass

    raise ValueError("Incorrectly formatted number of arguments")


def _extract_optional_argument(node):
    # Unwrap once internally if applicable
    n = _filter_children(node, False)
    if isinstance(n, BracketNode):
        node = n

    new_node = GroupNode()
    new_node.take(node)
    return new_node


def _get_bracket_args(it):
    temp = read_next(it)

    # A number of arguments was specified
    args = 0
    if isinstance(temp, TextNode) and temp.data == '[':
        temp = _read_until_end_bracket(it)
        args = _extract_arguments(temp)
        temp = read_next(it)

    # A default value was specified
    default = None
    if isinstance(temp, TextNode) and temp.data == '[':
        temp = _read_until_end_bracket(it)
        default = _extract_optional_argument(temp)
        temp = read_next(it)

    return args, default, temp


def _replace_parameters(root: GroupNode, params):
    def _do_replace(n, _):
        if isinstance(n, ParameterNode):
            if n.num_hashes == 1:
                # Replace with parameter value
                n.parent.take(params[n.param - 1].copy())
                return None
            else:
                n.num_hashes /= 2
                if int(n.num_hashes) != n.num_hashes:
                    raise ValueError("Number of hashes in parameter must be power of 2")

        return n

    return root.filter(_do_replace)


def _expand_macro(it, data, parent):
    args = data['args']
    tokens = []

    if data['args'] > 0:
        # Read in first argument, handling the default as required

        if data['default'] is not None:
            temp = read_next(it, False)
            if isinstance(temp, TextNode) and temp.data == '[':
                temp = _read_until_end_bracket(it)
                temp2 = _filter_children(temp, False)
                if isinstance(temp2, BracketNode):
                    temp = temp2
                tokens.append(temp)
            else:
                tokens.append(data['default'])
                if temp:  # Just in case there are no tokens left
                    it.appendleft(temp)

            args -= 1

        # Read in the rest of the arguments
        for _ in range(args):
            tokens.append(read_next(it))

    # Replace the parameter tokens with the read-in parameters
    if callable(data['body']):
        temp = data['body'](*tokens)
    else:
        temp = _replace_parameters(data['body'], tokens)

    for c in reversed(temp.children):
        # Add to front of queue to process expansion
        # Has to be done in reverse because appendleft reverses order
        c.parent = parent
        it.appendleft(c)


def _process(n, children):
    if not n.parent:
        return n

    # Keep track of macros
    if n.parent.data is None:
        n.parent.data = {'macros': n.parent.parent.data['macros'], 'copied': False}
    macros = n.parent.data['macros']

    def _check_macros():
        # This is to avoid having to make many copies of the macros dict
        nonlocal macros
        if not n.parent.data['copied']:
            n.parent.data['copied'] = True
            macros = macros.copy()
            n.parent.data['macros'] = macros

    # Define or insert macros or environments
    if isinstance(n, CommandNode):
        if n.data in ('newcommand', 'renewcommand', 'providecommand'):
            # Read in the command data
            name = _read_command_name(children)
            args, default, temp = _get_bracket_args(children)
            body = GroupNode()
            body.take(temp)
            data = {'args': args, 'default': default, 'body': body}

            # Add data to macros dict
            if n.data == 'newcommand' and name in macros:
                raise ValueError("Newcommand used for existing command")
            elif n.data != 'providecommand' or name not in macros:
                _check_macros()
                macros[name] = data

            return None
        elif n.data in ('newenvironment', 'renewenvironment'):
            # Read in environment name
            temp = read_next(children)
            name = str(temp)
            if isinstance(temp, BracketNode):
                name = name[1:-1]

            # Read in number of args and default arg if available
            args, default, temp = _get_bracket_args(children)

            # Read in begin and end code
            begin_body = GroupNode()
            begin_body.take(temp)
            temp = read_next(children)
            end_body = GroupNode()
            end_body.take(temp)

            # Add data to macros dict
            if n.data == 'newenvironment' and name in macros:
                raise ValueError("Newenvironment used for existing environment")
            else:
                _check_macros()
                macros[name] = {'args': args, 'default': default, 'body': begin_body}
                macros[f"end{name}"] = {'args': 0, 'default': None, 'body': end_body}

            return None
        elif n.data in macros:
            _expand_macro(children, macros[n.data], n.parent)
            return None
        elif n.data in ('begin', 'end'):
            # Read in name
            temp = read_next(children)
            name = str(temp)
            if isinstance(temp, BracketNode):
                name = name[1:-1]

            if n.data == 'end':
                name = f"end{name}"

            # Insert macro if it exists
            if name in macros:
                _expand_macro(children, macros[name], n.parent)
                return None
            else:
                # Undo reading of name
                children.appendleft(temp)

    return n


class Demacro:
    """A utility to de-macro LaTeX files."""

    def __init__(self):
        self.macros = {}

    def demacro(self, root):
        """De-macro the input AST node and return it.  All found macros are collected in the
        macros field, which persists across demacro calls."""

        root.data = {'macros': self.macros, 'copied': False}
        root = root.filter(_process, False)
        self.macros = root.data['macros']
        return clear_data(root)

    def add_macros(self, macros, replace=False):
        """Adds macros to the list.  macros should be a dictionary containing the macro name as keys
        and a dictionary as its value.  Each dictionary must contain a body key which corresponds to the
        macro body string.  The optional key args specifies how many arguments the macro takes.  The optional
        key default is the default first argument if it wasn't specified.  Environments can also be added
        using this function."""

        for k, v in macros.items():
            macro = {'args': 0, 'default': None}

            # Handle body argument, valid options: LaTeX text or a custom function
            if callable(v['body']):
                body = v['body']
                macro['args'] = len(signature(body).parameters)
            else:
                body = GroupNode()
                temp = to_ast(text=v['body'])
                body.take(temp)

            macro['body'] = body

            # Read in rest of parameters
            if 'args' in v:
                macro['args'] = v['args']
            if 'default' in v:
                macro['default'] = _extract_optional_argument(to_ast(text=v['default']))

            if replace or k not in self.macros:
                self.macros[k] = macro
