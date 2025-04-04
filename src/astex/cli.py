import os
from astex.ast import to_ast
from .demacro import Demacro

import argparse

# used for debugging
from ipydex import IPS, activate_ips_on_exception

activate_ips_on_exception()


def demacro():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="input file path")
    parser.add_argument("output", help="input file path")

    parser.add_argument("-rm", "--remove-macros", help="space-separated list of macros to remove", nargs="+")

    args = parser.parse_args()

    doc = to_ast(file=args.input)
    dm = Demacro()

    # Note: this currently ony handles simple macros like
    # \newcommand{\tcblue}[1]{\textcolor{blue}{#1}}

    macro_items = []
    for macro_name in args.remove_macros:
        macro_items.append((macro_name, {"body": "#1", "args": 1}))

        dm.add_macros(dict(macro_items))

    doc_dm = dm.demacro(doc)

    if os.path.exists(args.output):
        raise FileExistsError(args.output)
    with open(args.output, "w") as fp:
        fp.write(str(doc_dm))

    print(f"File written: {args.output}")
