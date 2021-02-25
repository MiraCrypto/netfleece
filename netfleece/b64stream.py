"""
b64stream provides the Base64Stream module.

Base64Stream wraps around any object with a read() method that returns
bytes, and provides a new read() method that returns base64 decoded
bytes instead. It does not support seek or any the usual streaming
methods.
"""

import base64
from math import ceil


class Base64Stream:
    # pylint: disable=too-few-public-methods
    """
    Base64Stream is a stream-like reader wrapper for Base64 encoded streams.

    Given a stream-like object with a read() method that returns bytes,
    Base64Stream will wrap it and provide a decoded stream with its own
    read method.

    :param stream: The base64 encoded stream to wrap
    """
    def __init__(self, stream):
        self._stream = stream
        self._buffer = bytes()

    def _enqueue(self, ndecodedbytes=-1):
        """
        _enqueue fills the decoded buffer by ndecodedbytes number of bytes.

        If ndecodedbytes is -1 or not specified, _enqueue will read an
        unbounded number of bytes via read() to the backing stream.

        :param ndecodedbytes: Number of decoded bytes to enqueue;
                              -1 for unbounded.
        """
        if ndecodedbytes >= 0:
            nbytes = ceil(ndecodedbytes / 3) * 4
        else:
            nbytes = -1
        data = self._stream.read(nbytes)
        # NB; len(data) can exceed nbytes when bytes is -1.
        if len(data) < nbytes:
            raise Exception('Unexpected EOF of base64 stream; '
                            'stream was not a multiple of 4 bytes?')
        decoded = base64.b64decode(data)
        assert len(decoded) >= ndecodedbytes
        self._buffer = self._buffer + decoded

    def _multipop(self, nbytes):
        """
        _multipop returns nbytes number of decoded bytes from the buffer.

        :param nbytes: Number of decoded bytes to remove and return.
        """
        res = self._buffer[:nbytes]
        self._buffer = self._buffer[nbytes:]
        return res

    def _empty(self):
        """_empty returns all remaining bytes from the decoded buffer."""
        res = self._buffer
        self._buffer = bytes()
        return res

    def read(self, size=-1):
        """
        read returns `size` number of base64 decoded bytes.

        read will buffer extra data to maintain base64 alignment (always
        reading in chunks of four bytes at a time per every three
        decoded characters.)

        if size is not specified or -1, read will perform an unbounded read
        of the backing stream's read() method, and return the entire decoded
        buffer.

        :param size: Number of decoded bytes to read from stream;
                     -1 for unbounded number of bytes.
        """
        if size and size >= 0:
            if size > len(self._buffer):
                rem = size - len(self._buffer)
                self._enqueue(rem)
            assert len(self._buffer) >= size
            return self._multipop(size)
        self._enqueue(size)
        return self._empty()
