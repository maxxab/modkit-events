"""Best-effort diagnostics for legacy failure and cleanup paths."""


def error_text(error: BaseException) -> str:
    """Diagnostic conversion must not prevent the selected disposition."""
    try:
        # Normalize str subclasses so later clipping cannot invoke user code.
        return str.__str__(str(error))
    except BaseException:
        return "Exception text unavailable"


def add_failure_note(
    original: BaseException, message: str, cleanup: BaseException | None = None
) -> None:
    """Neither rendering nor a custom add_note may replace the primary error."""
    try:
        if cleanup is not None:
            message = f"{message}: {type(cleanup).__name__}: {error_text(cleanup)}"
        original.add_note(message)
    except BaseException:
        pass
