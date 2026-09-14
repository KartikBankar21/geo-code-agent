from dataclasses import dataclass

from packages.execution.ast_parser import parse_code
from packages.execution.import_policy import validate_imports
from packages.execution.dangerous_policy import validate_dangerous_operations


@dataclass
class ValidationResult:
    valid: bool
    syntax_valid: bool
    syntax_error: str | None
    import_violations: list[str]
    dangerous_operations: list[str]


def validate_code(code: str) -> ValidationResult:
    """Validate generated Python code before execution."""

    try:
        tree = parse_code(code)
    except SyntaxError as e:
        return ValidationResult(
            valid=False,
            syntax_valid=False,
            syntax_error=f"{e.msg} (line {e.lineno}, column {e.offset})",
            import_violations=[],
            dangerous_operations=[],
        )

    import_violations = validate_imports(tree)
    dangerous_operations = validate_dangerous_operations(tree)

    valid = not import_violations and not dangerous_operations

    return ValidationResult(
        valid=valid,
        syntax_valid=True,
        syntax_error=None,
        import_violations=import_violations,
        dangerous_operations=dangerous_operations,
    )