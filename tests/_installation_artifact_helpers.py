"""Test-only historical prefix view; never changes migration bytes on disk."""

CURRENT_HEADER = (
    b"-- Events initial schema for explicit owner installation.\n"
    b"-- Caller owns the transaction; installation requires a matching independently qualified closure.\n"
    b"-- This source alone does not establish installation or runtime qualification.\n"
)
HISTORICAL_HEADER = (
    b"-- NEW initial schema SOURCE IN PROGRESS. NOT READY TO APPLY.\n"
    b"-- Partial private validators and core records; public functions/grants still pending.\n"
    b"-- Bounded SQL checks do not qualify this complete migration. Application owns transaction.\n"
)


def historical_prefix_view(raw: bytes) -> bytes:
    """Validate all three current comments and restore only their historical bytes."""
    if type(raw) is not bytes or not raw.startswith(CURRENT_HEADER):
        raise ValueError("unexpected installation header")
    return HISTORICAL_HEADER + raw[len(CURRENT_HEADER):]


def test_header_view_preserves_every_suffix_byte():
    suffix = b"\nSELECT 'unchanged';\x00\xff"
    raw = CURRENT_HEADER + suffix
    assert historical_prefix_view(raw) == HISTORICAL_HEADER + suffix
    assert raw == CURRENT_HEADER + suffix


def test_header_view_rejects_noncanonical_input():
    import pytest

    for raw in (
        b"", HISTORICAL_HEADER, CURRENT_HEADER[:-1],
        CURRENT_HEADER.replace(b"Events", b"events", 1),
        CURRENT_HEADER.replace(b"\n", b"\r\n"),
        b" " + CURRENT_HEADER, bytearray(CURRENT_HEADER), None,
    ):
        with pytest.raises(ValueError, match="unexpected installation header"):
            historical_prefix_view(raw)
