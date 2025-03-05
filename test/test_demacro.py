import unittest

from astex.demacro import *
from astex.ast import to_ast, GroupNode


TEST_LATEX = r"""
\newcommand{\foo}[2][{bar}]{#1 = #2}
\newcommand*{\bar}{Bar}
\newenvironment{testenv}[1]{start #1}{end}

\begin{document}
\begin{testenv}{\LaTeX}
\test[hello]
\newtest{goodbye}
\foo[foo]{baz}
\foo{baz}
\end{testenv}

\code
\end{document}
""".strip()


TEST_OUTPUT = r"""
\begin{document}
start \LaTeX

hello = goodbye
foo = baz
bar = baz
end


\end{document}
""".strip()


class TestDemacro(unittest.TestCase):
    def test(self):
        root = to_ast(text=TEST_LATEX)
        dm = Demacro()
        dm.add_macros({"test": {"body": r"\newcommand{\newtest}[1]{#1 = ##1}", "args": 1, "default": "test"}})
        dm.add_macros({"code": {"body": lambda: GroupNode()}})
        self.assertEqual(str(dm.demacro(root)).strip(), TEST_OUTPUT)

