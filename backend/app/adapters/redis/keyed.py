"""Rows written as keys of their own, each replacing its key whole (D314).

One script a key, run on the server: the type is checked and the key
replaced with nothing in between, so a list somebody keeps under a name a row
happens to match is left alone rather than destroyed. The scripts of a block
go in one pipeline, which is round trips saved, not a transaction across keys.
"""

from redis.asyncio.client import Pipeline

from app.adapters.keyed import KeyedRow, KeyedWriteRequest, KeyedWritten
from app.adapters.protocol import NodeNotFound
from app.adapters.redis.keyspace import MAX_STRING_BYTES, RedisKeyspace, place_of
from app.adapters.redis.session import RedisSession
from app.core.translation import say

# KEYS[1] the key; ARGV[1] its time to live, 0 for none; ARGV[2] the value.
_STRING = """
local found = redis.call('TYPE', KEYS[1]).ok
if found ~= 'none' and found ~= 'string' then return 0 end
if ARGV[1] == '0' then
  redis.call('SET', KEYS[1], ARGV[2])
else
  redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[1])
end
return 1
"""

# KEYS[1] the key; ARGV[1] its time to live; ARGV[2..] field, value, ...
_HASH = """
local found = redis.call('TYPE', KEYS[1]).ok
if found ~= 'none' and found ~= 'hash' then return 0 end
redis.call('DEL', KEYS[1])
redis.call('HSET', KEYS[1], unpack(ARGV, 2))
if ARGV[1] ~= '0' then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return 1
"""


def _last_per_key(request: KeyedWriteRequest) -> tuple[dict[str, list[str]], int]:
    """Each key's arguments from the last row naming it, and the rows that
    name no key or hold nothing."""
    latest: dict[str, list[str]] = {}
    without = 0
    hashed = len(request.fields) > 1
    for row in request.rows:
        arguments = _arguments(request, row, hashed)
        if row.key is None or row.key == "" or arguments is None:
            without += 1
            continue
        name = request.prefix + row.key
        # Placed again at the end: the last row for a key is the one written.
        latest.pop(name, None)
        latest[name] = arguments
    return latest, without


def _arguments(
    request: KeyedWriteRequest, row: KeyedRow, hashed: bool
) -> list[str] | None:
    pairs = [
        (field, value)
        for field, value in zip(request.fields, row.values, strict=True)
        if value is not None and value != ""
    ]
    for _, value in pairs:
        if len(value.encode()) > MAX_STRING_BYTES:
            raise ValueError(
                say(
                    "The value for {key} is longer than {limit} bytes",
                    key=request.prefix + (row.key or ""),
                    limit=MAX_STRING_BYTES,
                )
            )
    if not pairs:
        return None
    if not hashed:
        return [pairs[0][1]]
    return [part for pair in pairs for part in pair]


class RedisKeyed:
    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._session = session
        self._keyspace = keyspace

    def keyed_prefix(self, node_id: str | None) -> str | None:
        """The prefix a place gives its keys, or None for what is not a place."""
        try:
            return place_of(node_id).prefix
        except NodeNotFound:
            return None

    async def write_keyed(self, request: KeyedWriteRequest) -> KeyedWritten:
        for row in request.rows:
            if len(row.values) != len(request.fields):
                raise ValueError(say("Each row needs a value for every field"))
        place = place_of(request.place_node_id)
        latest, without = _last_per_key(request)
        if not latest:
            return KeyedWritten(written=0, without_key=without)
        ttl = str(request.ttl_seconds or 0)
        hashed = len(request.fields) > 1
        async with self._session.connection(place.database) as client:
            script = client.register_script(_HASH if hashed else _STRING)
            pipe: Pipeline = client.pipeline(transaction=False)
            for name, arguments in latest.items():
                await script(keys=[name], args=[ttl, *arguments], client=pipe)
            answers: list[object] = await pipe.execute()
        written = sum(1 for answer in answers if answer == 1)
        return KeyedWritten(
            written=written, without_key=without, other_type=len(answers) - written
        )
