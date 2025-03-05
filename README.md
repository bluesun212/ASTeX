# ASTeX - a (La)TeX AST transformer and de-macro tool
For various reasons, it can be useful or even necessary to process/modify LaTeX files in an automated way so they can be understood by programs that can only handle a subset of LaTeX.  For example, pandoc, KaTeX, and MathJax can exhibit very surprising behaviors even when handle seemingly common LaTeX constructs, like certain math environments, reference handling, and line numbering.  Consider this use-case: you want to write an article in LaTeX that can both generate a .pdf and a webpage.  This is something that is seemingly becoming more common, with organizations such as IEEE offering both a .pdf download and a webpage "preview" of papers that appear in their journals.  For performance reasons, it may be desired to statically generate a portion of the beginning of the text, then have the rest of the math be rendered dynamically with JavaScript.  This tool was created to function as a preprocessor to these aforementioned programs and output LaTeX that can be processed in a way we expect it should in these use cases.  

There are two aspects to this project: the abstract syntax tree (AST) transformer, and the de-macro tool.  The AST capabilities are found in the ```ast.py``` file and include routines to convert LaTeX to and from its AST form and to modify the tree using filters, some of which are included in the file itself.  The de-macro tool code is located in the ```demacro.py``` file and includes a ```Demacro``` class to read and expand custom macros and environments.  The following code snippets show these capabilities in action.  

### AST modification
The following is a simple example that capitalizes all commands in a file named ```test.tex```.  More examples can be found in the ```test``` folder.  

```python
from astex.ast import *


def _capitalize_commands(node, next_nodes):
    if isinstance(node, CommandNode):
        # Replace current node with a CommandNode with capitalized letters
        return CommandNode(node.data.upper())  

    return None  # Makes no changes to the current node

#  Read the text from test.tex, convert to an AST, and return the root node
root = to_ast(file="test.tex")

# Run the above filter on the tree
root = root.filter(_capitalize_commands)

# __str__ converts the tree back into a string
print(root)  
```

### The de-macro tool
The following example loads macro definitions from ```defs.tex```, adds a macro programatically, then replaces the macros in ```paper.tex``` and prints the result.

```python
from astex.ast import to_ast
from ast.demacro import Demacro


#  Load AST from a file containing macro definitions and a file we want to de-macro
defs = to_ast(file="defs.tex")
root = to_ast(file="paper.tex")

dm = Demacro()

# Process the macros in the defs file.  The macros will be applied on all future files.
dm.demacro(defs)  

# Equivalent to \newcommand{\test}[1]{testing #1}
dm.add_macros({"test": {"body": "testing #1", "args": 1}})  

# Demacro the paper file with the previously loaded macro definitions
root = dm.demacro(root)  

# Print out de-macro'ed result
print(root)
```
