import ast


DANGEROUS_FUNCTIONS = {
    "eval",
    "exec",
    "open",
    "__import__",
}


DANGEROUS_METHODS = {
    # OS / shell execution
    ("os", "system"),
    ("os", "popen"),

    # Process spawning / replacement
    ("os", "fork"),
    ("os", "kill"),
    ("os", "execl"),
    ("os", "execle"),
    ("os", "execlp"),
    ("os", "execlpe"),
    ("os", "execv"),
    ("os", "execve"),
    ("os", "execvp"),
    ("os", "execvpe"),
    ("os", "spawnl"),
    ("os", "spawnv"),

    # Direct filesystem deletion
    ("os", "remove"),
    ("os", "unlink"),
    ("os", "rmdir"),

    # Process execution
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),

    # pathlib destructive operations
    ("Path", "unlink"),
    ("Path", "rmdir"),
    ("Path", "rename"),
    ("Path", "replace"),
}


def _collect_aliases(tree: ast.AST):
    """
    Walk the tree once and build two lookup tables so later checks can
    resolve a *local* name back to what it actually refers to, regardless
    of aliasing:

    import_aliases:
        local name -> real top-level module
        e.g. `import os as x`            -> {"x": "os"}

    from_aliases:
        local name -> (defining module, real symbol name)
        e.g. `from os import system`     -> {"system": ("os", "system")}
        e.g. `from pathlib import Path`  -> {"Path": ("pathlib", "Path")}
    """

    import_aliases: dict[str, str] = {}
    from_aliases: dict[str, tuple[str, str]] = {}

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                import_aliases[local] = alias.name

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            for alias in node.names:
                local = alias.asname or alias.name
                from_aliases[local] = (module, alias.name)

    return import_aliases, from_aliases


def validate_dangerous_operations(tree: ast.AST) -> list[str]:
    """Return dangerous operations found in the AST.

    Import aliases are resolved first, so renaming an import (or
    importing a dangerous symbol directly via `from ... import ...`)
    cannot be used to slip past the literal-name checks below.
    """

    import_aliases, from_aliases = _collect_aliases(tree)

    violations = []

    for node in ast.walk(tree):

        if not isinstance(node, ast.Call):
            continue

        operation = _get_operation(
            node.func,
            import_aliases,
            from_aliases,
        )

        if operation is None:
            continue

        if isinstance(operation, tuple):
            module, name = operation

            if operation in DANGEROUS_METHODS:
                violations.append(f"{module}.{name}")

            elif name in DANGEROUS_FUNCTIONS:
                violations.append(
                    f"{module}.{name}" if module else name
                )

        elif operation in DANGEROUS_FUNCTIONS:
            violations.append(operation)

    return violations


def _get_operation(
    node: ast.AST,
    import_aliases: dict[str, str],
    from_aliases: dict[str, tuple[str, str]],
):
    """
    Extract a function or module.method call from an AST node, resolving
    any import aliases along the way.

    Examples:
        exec(...)                          -> "exec"
        os.system(...)                     -> ("os", "system")
        import os as x; x.system(...)      -> ("os", "system")
        from os import system; system(...) -> ("os", "system")
        Path("file").unlink()              -> ("Path", "unlink")
        from pathlib import Path as P
        P("file").unlink()                 -> ("Path", "unlink")
    """

    if isinstance(node, ast.Name):
        if node.id in from_aliases:
            return from_aliases[node.id]

        return node.id

    if isinstance(node, ast.Attribute):

        if isinstance(node.value, ast.Name):
            module = import_aliases.get(node.value.id, node.value.id)
            return module, node.attr

        # Handle calls such as:
        # Path("file").unlink()
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                local_name = node.value.func.id
                real_name = from_aliases.get(
                    local_name,
                    (None, local_name),
                )[1]

                return real_name, node.attr

    return None
