import asyncio
import logging
import os
from time import sleep
from uuid import UUID

from model import HTTPException, PersonWrite
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import ValidationError
from redis.asyncio import ConnectionPool, StrictRedis
from robyn import Headers, Request, Response, Robyn, jsonify

app = Robyn(__file__)

INSERT = (
    "INSERT INTO pessoa (id, apelido, nome, nascimento, stack) VALUES (%(id)s, %(apelido)s, %(nome)s, "
    "%(nascimento)s, %(stack)s) ON conflict (apelido) do update set id = excluded.id, apelido = excluded.apelido, nome = excluded.nome, nascimento = excluded.nascimento, stack = excluded.stack"
)
SELECT_BY_ID = "SELECT id, apelido, nome, nascimento, stack FROM pessoa p WHERE p.id = %(id)s LIMIT 1"
SELECT_BY_TERM = "SELECT id, apelido, nome, nascimento, stack FROM pessoa p WHERE p.search LIKE %s LIMIT 50"
SELECT_COUNT = "SELECT count(*) FROM pessoa"

insert_queue = asyncio.Queue()


async def startup():
    logging.warning("Waiting 5 seconds to start database pool...")
    sleep(5)
    global pool
    max_connections = int(os.getenv("DATABASE_POOL_SIZE", 10))
    pool = AsyncConnectionPool(
        conninfo=os.environ["DATABASE_URL"], max_size=max_connections, min_size=10, max_idle=50, timeout=60
    )

    global redis_pool
    host = os.getenv("REDIS_HOST", "localhost")
    redis_pool = ConnectionPool.from_url(f"redis://{host}")

    asyncio.create_task(worker())
    logging.warning("Database pool started!")


async def shutdown():
    logging.warning("Closing database pool...")
    await pool.close()
    logging.warning("Database pool closed!")

    logging.warning("Closing redis pool...")
    await redis_pool.disconnect()


app.startup_handler(startup)
app.shutdown_handler(shutdown)


@app.post("/pessoas")
async def create_pessoa(request: Request):
    try:
        person = PersonWrite.model_validate_json(request.body)
        redis = StrictRedis(connection_pool=redis_pool, encoding="utf-8", decode_responses=True)
        if await redis.get(person.apelido):
            return Response(status_code=400, headers=Headers({}), description="")

        await redis.set(person.apelido, "ok")
        await redis.set(str(person.id), person.model_dump_json())
        await insert_queue.put(person.model_dump())
        return Response(status_code=201, headers=Headers({"location": f"/pessoas/{person.id}"}), description="OK")
    except ValidationError:
        return Response(status_code=422, headers=Headers({}), description="")
    except (HTTPException, UniqueViolation):
        return Response(status_code=400, headers=Headers({}), description="")


@app.get("/pessoas/:id")
async def get_pessoa(request: Request):
    try:
        id = UUID(request.path_params.get("id"))
        redis = StrictRedis(connection_pool=redis_pool, encoding="utf-8", decode_responses=True)
        if person := await redis.get(str(id)):
            return person

    except ValueError:
        ...
    return Response(status_code=404, headers=Headers({}), description="")


@app.get("/pessoas")
async def get_pessoas(request: Request):
    term = request.query_params.get("t")
    if term:
        async with pool.connection() as conn:
            cur = await conn.cursor(row_factory=dict_row).execute(SELECT_BY_TERM, (f"%{term}%",))
            people = await cur.fetchall()
            return jsonify(people)

    return Response(status_code=400, headers=Headers({}), description="Invalid")


@app.get("/contagem-pessoas")
async def get_contagem_pessoas(request: Request):
    await asyncio.sleep(3)
    async with pool.connection() as conn:
        cur = await conn.cursor().execute(SELECT_COUNT)
        count = (await cur.fetchone())[0]
    return count


async def worker():
    batch_size = 100
    batch_timeout = 1

    while True:
        batch = []
        while len(batch) < batch_size:
            try:
                person = await asyncio.wait_for(insert_queue.get(), timeout=batch_timeout)
                if person:
                    batch.append(person)
            except asyncio.TimeoutError:
                break
        if batch:
            await insert_into_db(batch)


async def insert_into_db(persons):
    logging.warning(f"Inserting {len(persons)} persons into database...")
    async with pool.connection() as conn:
        async with conn.transaction() as t:
            cur = t.connection.cursor()
            await cur.executemany(INSERT, persons)


app.start(host=os.getenv("ROBYN_HOST", "127.0.0.1"), port=os.getenv("ROBYN_PORT", 80))
