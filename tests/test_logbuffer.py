"""Tests for the LogBuffer in-memory log ring buffer."""

import logging

from agent0.logbuffer import LogBuffer


class TestLogBufferEmit:
    def test_records_message(self) -> None:
        buf = LogBuffer(maxlen=100)
        record = logging.LogRecord('test', logging.INFO, '', 0, 'hello', (), None)
        buf.emit(record)

        result = buf.get_entries()
        assert len(result['entries']) == 1
        assert result['entries'][0]['message'] == 'hello'
        assert result['entries'][0]['level'] == 'INFO'

    def test_assigns_incrementing_ids(self) -> None:
        buf = LogBuffer(maxlen=100)
        for i in range(5):
            record = logging.LogRecord('test', logging.INFO, '', 0, f'msg{i}', (), None)
            buf.emit(record)

        result = buf.get_entries()
        ids = [e['id'] for e in result['entries']]
        assert ids == [1, 2, 3, 4, 5]

    def test_respects_maxlen(self) -> None:
        buf = LogBuffer(maxlen=3)
        for i in range(10):
            record = logging.LogRecord('test', logging.INFO, '', 0, f'msg{i}', (), None)
            buf.emit(record)

        result = buf.get_entries()
        assert len(result['entries']) == 3
        assert result['last_id'] == 10
        assert result['entries'][0]['message'] == 'msg7'

    def test_includes_timestamp(self) -> None:
        buf = LogBuffer(maxlen=100)
        record = logging.LogRecord('test', logging.WARNING, '', 0, 'warn', (), None)
        buf.emit(record)

        entry = buf.get_entries()['entries'][0]
        assert 'timestamp' in entry

    def test_includes_logger_name(self) -> None:
        buf = LogBuffer(maxlen=100)
        record = logging.LogRecord('mymodule', logging.DEBUG, '', 0, 'debug', (), None)
        buf.emit(record)

        entry = buf.get_entries()['entries'][0]
        assert entry['logger'] == 'mymodule'


class TestLogBufferGetEntries:
    def test_after_cursor(self) -> None:
        buf = LogBuffer(maxlen=100)
        for i in range(5):
            record = logging.LogRecord('test', logging.INFO, '', 0, f'msg{i}', (), None)
            buf.emit(record)

        result = buf.get_entries(after=3)
        assert len(result['entries']) == 2
        assert result['entries'][0]['id'] == 4
        assert result['entries'][1]['id'] == 5

    def test_level_filter(self) -> None:
        buf = LogBuffer(maxlen=100)
        buf.emit(logging.LogRecord('test', logging.DEBUG, '', 0, 'debug', (), None))
        buf.emit(logging.LogRecord('test', logging.INFO, '', 0, 'info', (), None))
        buf.emit(logging.LogRecord('test', logging.WARNING, '', 0, 'warn', (), None))
        buf.emit(logging.LogRecord('test', logging.ERROR, '', 0, 'error', (), None))

        result = buf.get_entries(level='WARNING')
        assert len(result['entries']) == 2
        levels = [e['level'] for e in result['entries']]
        assert levels == ['WARNING', 'ERROR']

    def test_combined_after_and_level(self) -> None:
        buf = LogBuffer(maxlen=100)
        buf.emit(logging.LogRecord('test', logging.DEBUG, '', 0, 'debug', (), None))
        buf.emit(logging.LogRecord('test', logging.WARNING, '', 0, 'warn', (), None))
        buf.emit(logging.LogRecord('test', logging.INFO, '', 0, 'info', (), None))
        buf.emit(logging.LogRecord('test', logging.ERROR, '', 0, 'error', (), None))

        result = buf.get_entries(after=2, level='WARNING')
        assert len(result['entries']) == 1
        assert result['entries'][0]['level'] == 'ERROR'

    def test_empty_buffer(self) -> None:
        buf = LogBuffer(maxlen=100)
        result = buf.get_entries()
        assert result == {'entries': [], 'last_id': 0}

    def test_last_id_reflects_total_emitted(self) -> None:
        buf = LogBuffer(maxlen=3)
        for i in range(10):
            record = logging.LogRecord('test', logging.INFO, '', 0, f'msg{i}', (), None)
            buf.emit(record)

        result = buf.get_entries(after=9)
        assert result['last_id'] == 10
        assert len(result['entries']) == 1

    def test_case_insensitive_level(self) -> None:
        buf = LogBuffer(maxlen=100)
        buf.emit(logging.LogRecord('test', logging.ERROR, '', 0, 'err', (), None))
        buf.emit(logging.LogRecord('test', logging.DEBUG, '', 0, 'dbg', (), None))

        result = buf.get_entries(level='error')
        assert len(result['entries']) == 1
        assert result['entries'][0]['level'] == 'ERROR'
