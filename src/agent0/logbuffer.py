import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

__all__ = ['LogBuffer']

LEVEL_VALUES = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
}


class LogBuffer(logging.Handler):

    '''
    Compute in-memory ring buffer of recent log records for API exposure.

    Args:
        maxlen (int): Maximum number of log entries to retain

    Returns:
        LogBuffer: Logging handler with queryable buffer
    '''

    def __init__(self, maxlen: int = 1000) -> None:
        super().__init__()
        self._buffer: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._counter = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:

        '''
        Compute log entry from record and append to buffer.

        Args:
            record (logging.LogRecord): Standard logging record

        Returns:
            None
        '''

        with self._lock:
            self._counter += 1
            self._buffer.append({
                'id': self._counter,
                'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                'level': record.levelname,
                'logger': record.name,
                'message': self.format(record) if self.formatter else record.getMessage(),
            })

    def get_entries(
        self,
        after: int = 0,
        level: str = 'DEBUG',
    ) -> dict[str, Any]:

        '''
        Compute log entries newer than the given cursor.

        Args:
            after (int): Return entries with id strictly greater than this value
            level (str): Minimum log level to include

        Returns:
            dict[str, Any]: Dict with entries list and last_id cursor
        '''

        min_level = LEVEL_VALUES.get(level.upper(), logging.DEBUG)

        with self._lock:
            entries = [
                e for e in self._buffer
                if e['id'] > after
                and LEVEL_VALUES.get(e['level'], logging.DEBUG) >= min_level
            ]
            last_id = self._counter

        return {'entries': entries, 'last_id': last_id}
