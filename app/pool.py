import asyncio

from pysqlx_engine import PySQLXEngine
from redis.asyncio import StrictRedis

# create a class connection pool using the PySQLXEngine and asyncio.queue to manage the connections


class PySQLXPool:
    def __init__(self, uri: str, max_size: int = 10):
        self._uri = uri
        self._max_size = max_size
        self._pool = asyncio.Queue(maxsize=self._max_size)

    async def connect(self):
        for _ in range(self._max_size):
            db = PySQLXEngine(uri=self._uri)
            await db.connect()
            await self._pool.put(db)

    async def close(self):
        for _ in range(self._max_size):
            db = await self._pool.get()
            await db.close()

    async def get(self) -> PySQLXEngine:
        return await self._pool.get()

    async def put(self, db: PySQLXEngine):
        await self._pool.put(db)


# create a class connection pool using the StrictRedis and asyncio.queue to manage the connections
class RedisPool:
    def __init__(self, host: str, max_size: int = 10):
        self._host = host
        self._max_size = max_size
        self._pool = asyncio.Queue(maxsize=self._max_size)

    async def connect(self):
        for _ in range(self._max_size):
            db = StrictRedis(host=self._host, port=6379, db=0)
            await self._pool.put(db)

    async def close(self):
        for _ in range(self._max_size):
            db = await self._pool.get()
            await db.close()

    async def get(self) -> StrictRedis:
        return await self._pool.get()

    async def put(self, db: StrictRedis):
        await self._pool.put(db)
