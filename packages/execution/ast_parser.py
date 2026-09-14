import ast


def parse_code(code: str) -> ast.Module:
    """Parse Python source code into an AST."""
    return ast.parse(code)