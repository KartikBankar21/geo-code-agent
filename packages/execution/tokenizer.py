import tokenize
from io import StringIO


def tokenize_code(code: str):
    """Tokenize Python source code."""
    return list(tokenize.generate_tokens(StringIO(code).readline))