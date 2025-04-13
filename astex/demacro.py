# Future ideas:
# - option to strip comments
# - option to expand \include or look into \usepackage for macros
# - Handling \def, \let, etc
# - Dealing with paragraph breaks in commands
from .ast import *
from .utils import *
from inspect import signature

__all__ = ['Demacro']


# Newcommand-related ones
def _read_command_name(it):
    # Ignore stars for now, TODO
    n = read_next(it)
    if isinstance(n, TextNode) and n.data == '*':
        n = read_next(it)

    # Extract command name
    if isinstance(n, GroupNode):
        n = read_next(n.children)

    if isinstance(n, CommandNode):
        return n.data

    raise ValueError("Incorrectly formatted command name")


def _get_bracket_args(it):
    def _to_args(node):
        a = int(str(node))
        if 0 <= a < 9:
            return a
        raise ValueError("Incorrectly formatted number of arguments")

    # A number of arguments was specified
    args = 0
    temp = read_bracket_arg(it)
    if temp:
        args = _to_args(temp)

    default = read_bracket_arg(it)
    temp = read_next(it)

    return args, default, temp


def _expand_macro(it, data, parent):
    args = data['args']
    tokens = []

    if args > 0:
        # Read in first argument, handling the default as required

        if data['default'] is not None:
            temp = read_bracket_arg(it)
            if temp:
                tokens.append(temp)
            else:
                tokens.append(data['default'])

            args -= 1

        # Read in the rest of the arguments
        for _ in range(args):
            tokens.append(read_next(it))

    # Replace the parameter tokens with the read-in parameters
    if callable(data['body']):
        temp = GroupNode()
        ret = data['body'](parent, it, *tokens)
        if ret:  # In case None was returned
            temp.take(ret)
    else:
        temp = replace_parameters(data['body'].copy(), tokens)

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
    elif isinstance(n, EnvironmentNode) and n.name in macros:
        # Expand \end macro, we have to do this first because we add to the head of the deque
        _expand_macro(children, macros[f"end{n.name}"], n.parent)

        # Read arguments then expand \begin macro in new deque in front of all internal tokens
        _expand_macro(n.children, macros[n.name], n)

        # Now add that deque in front
        for temp in reversed(n.children):
            temp.parent = n.parent
            children.appendleft(temp)

        return None

    return n


class Demacro:
    """A utility to de-macro LaTeX files."""

    def __init__(self):
        self.macros = {}

    def demacro(self, root: GroupNode) -> GroupNode:
        """De-macro the input AST node and return it.  All found macros are collected in the
        macros field, which persists across demacro calls."""

        root.data = {'macros': self.macros, 'copied': False}
        root = root.filter(_process)
        self.macros = root.data['macros']
        return clear_data(root)

    @staticmethod
    def expand_unsafe(root):
        return root.filter(_process)

    def add_macros(self, macros: dict, replace=False):
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
            elif isinstance(v['body'], GroupNode):
                body = v['body']
            else:
                body = GroupNode()
                temp = to_ast(text=v['body'])
                body.take(temp)

            macro['body'] = body

            # Read in rest of parameters
            if 'args' in v:
                macro['args'] = v['args']
            if 'default' in v:
                macro['default'] = v['default']
            if macro['default'] is not None:
                macro['default'] = to_ast(text=macro['default'])

            if replace or k not in self.macros:
                self.macros[k] = macro

    def add_environments(self, envs, replace=False):
        macros = {}
        for k, v in envs.items():
            macros[f"end{k}"] = {'body': v['end']}
            macros[k] = {'body': v['start'], 'args': v.get('args', 0), 'default': v.get('default')}

        self.add_macros(macros, replace)
