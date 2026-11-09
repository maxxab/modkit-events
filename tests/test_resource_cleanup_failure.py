"""Bounded controls for first-primary preservation at resource cleanup boundaries."""

import io
import types
import zipfile

import pytest

from modkit_events.persistence import _resource_io as resource


class NotesFailure(BaseException):
    def __getattribute__(self, name):
        if name == '__notes__':
            raise MemoryError('controlled annotation failure')
        return super().__getattribute__(name)


def _primary(mode, suppressed):
    error = NotesFailure('primary') if mode == 'allocation' else BaseException('primary')
    if mode == 'invalid':
        error.__notes__ = 'not a list'
    error.__cause__ = ValueError('original cause')
    error.__context__ = LookupError('original context')
    error.__suppress_context__ = suppressed
    return error


def _raise_received(error, received):
    try:
        raise error
    except BaseException:
        received.append(error.__traceback__)
        raise


def _assert_primary(escaped, primary, received, metadata, mode):
    assert escaped is primary
    assert escaped.__cause__ is metadata[0]
    assert escaped.__context__ is metadata[1]
    assert escaped.__suppress_context__ is metadata[2]
    traceback = escaped.__traceback__
    while traceback is not None and traceback is not received[0]:
        traceback = traceback.tb_next
    assert traceback is received[0], 'received traceback suffix was replaced'
    if mode == 'invalid':
        assert escaped.__notes__ == 'not a list'
    elif mode == 'normal':
        assert escaped.__notes__ == [
            'Migration resource cleanup failed; close outcome is uncertain.'
        ]


def _zip_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('manifest.json', b'{}')
    return stream.getvalue()


def _zip_controls(monkeypatch, primary, received, attempts, failures):
    # Keep raw ZIP validation and stdlib metadata interpretation real. Only the
    # external close/result boundaries inject failures; backing is memory-only.
    class Stream:
        def __init__(self, data):
            self.inner = io.BytesIO(data)

        def close(self):
            attempts.append('stream')
            self.inner.close()
            raise failures[1]

    class Archive:
        def __init__(self, stream):
            self.inner = zipfile.ZipFile(stream.inner)

        def infolist(self):
            if primary is not None:
                _raise_received(primary, received)
            return self.inner.infolist()

        def close(self):
            attempts.append('archive')
            self.inner.close()
            raise failures[0]

    monkeypatch.setattr(resource, 'io', types.SimpleNamespace(BytesIO=Stream))
    monkeypatch.setattr(resource, 'zipfile', types.SimpleNamespace(
        ZipFile=Archive, BadZipFile=zipfile.BadZipFile,
    ))


@pytest.mark.parametrize('boundary', ['descriptor', 'zip'])
@pytest.mark.parametrize('mode', ['invalid', 'allocation', 'normal'])
@pytest.mark.parametrize('suppressed', [False, True])
def test_cleanup_annotation_never_replaces_primary(monkeypatch, boundary, mode, suppressed):
    primary = _primary(mode, suppressed)
    metadata = (primary.__cause__, primary.__context__, primary.__suppress_context__)
    received, attempts = [], []
    failures = (RuntimeError('first close'), KeyboardInterrupt('second close'))
    owned = [101, 102]
    if boundary == 'descriptor':
        def close(fd):
            attempts.append(fd)
            raise failures[0 if fd == 102 else 1]

        monkeypatch.setattr(resource, 'os', types.SimpleNamespace(close=close))

        def operation():
            try:
                _raise_received(primary, received)
            except BaseException as error:
                resource._cleanup(owned, error)
                raise
    else:
        data = _zip_bytes()
        _zip_controls(monkeypatch, primary, received, attempts, failures)

        def operation():
            resource.ZipLease(data, '')

    with pytest.raises(BaseException) as caught:
        operation()
    _assert_primary(caught.value, primary, received, metadata, mode)
    assert attempts == ([102, 101] if boundary == 'descriptor' else ['archive', 'stream'])
    if boundary == 'descriptor':
        assert owned == []
        resource._cleanup(owned, primary)
        assert attempts == [102, 101], 'detached ownership was retried'


@pytest.mark.parametrize('boundary', ['descriptor', 'zip'])
def test_without_primary_first_close_failure_prevents_success(monkeypatch, boundary):
    attempts, received = [], []
    failures = (KeyboardInterrupt('first close'), RuntimeError('second close'))
    if boundary == 'descriptor':
        def close(fd):
            attempts.append(fd)
            raise failures[0 if fd == 102 else 1]

        monkeypatch.setattr(resource, 'os', types.SimpleNamespace(close=close))
        owned = [101, 102]

        def operation():
            resource._cleanup(owned, None)
    else:
        data = _zip_bytes()
        _zip_controls(monkeypatch, None, received, attempts, failures)

        def operation():
            resource.ZipLease(data, '')

    with pytest.raises(BaseException) as caught:
        operation()
    assert caught.value is failures[0]
    assert attempts == ([102, 101] if boundary == 'descriptor' else ['archive', 'stream'])


def test_successful_resource_reads_remain_available(tmp_path):
    (tmp_path / 'manifest.json').write_bytes(b'{}')
    with resource.PosixLease(tmp_path) as lease:
        assert lease.read('manifest.json') == b'{}'
    with resource.ZipLease(_zip_bytes(), '') as lease:
        assert lease.read('manifest.json') == b'{}'
