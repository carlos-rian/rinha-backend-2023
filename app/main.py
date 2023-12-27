import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import TypeAdapter
from pysqlx_engine.errors import ExecuteError as ExecError

from app.model import BasePerson, PersonRead, PersonWrite
from app.pool import PySQLXPool, RedisPool

db_pool = PySQLXPool(uri=os.environ["DATABASE_URL"], max_size=int(os.environ.get("DATABASE_MAX_POOL_SIZE", 10)))
cache_pool = RedisPool(host=os.environ["REDIS_HOST"], max_size=int(os.environ.get("REDIS_MAX_POOL_SIZE", 10)))

insert_queue = asyncio.Queue()

INSERT = """
    INSERT INTO people (id, name, nick, birth_date, stack) VALUES {} 
    ON conflict (nick) do update set id = excluded.id, nick = excluded.nick, name = excluded.name, birth_date = excluded.birth_date, stack = excluded.stack;
"""
SELECT_BY_ID = "SELECT * FROM people WHERE id = :id;"
SELECT_BY_TERM = "SELECT * FROM people WHERE search ILIKE :term LIMIT 50;"
SELECT_COUNT = "SELECT COUNT(*) as qty FROM people"


async def insert_worker():
    batch_size = 200
    batch_timeout = 3

    def insert_formated(batch: list[PersonWrite]):
        insert = ",\n".join(
            map(lambda p: f"('{p.id}', '{p.name}', '{p.nick}', '{p.birth_date}', {p.stack_str})", batch)
        )
        return INSERT.format(insert)

    async def insert_batch(batch: list[PersonWrite]):
        db = await db_pool.get()
        try:
            await db.execute(sql=insert_formated(batch))
        except ExecError as err:
            logging.error(err)
        finally:
            await db_pool.put(db)

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
            await insert_batch(batch)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_pool.connect()
    await cache_pool.connect()
    coro = asyncio.create_task(insert_worker())
    yield
    await db_pool.close()
    await cache_pool.close()
    coro.cancel()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(RequestValidationError)
def handler_request_validation_error(_a: Request, _b: RequestValidationError) -> Response:
    return Response(status_code=422)


@app.post("/pessoas", status_code=201)
async def post_pessoa(body: PersonWrite, response: Response):
    cache = await cache_pool.get()
    if await cache.get(f"nick:{body.nick}"):
        return Response(status_code=400)

    await insert_queue.put(body)

    await cache.set(f"nick:{body.nick}", "ok")
    await cache.set(f"id:{body.id}", body.model_dump_json())
    await cache_pool.put(cache)

    response.headers["Location"] = f"/pessoas/{body.id}"
    response.status_code = 201
    return response


@app.get("/pessoas/{id}")
async def get_pessoa_by_id(id: UUID):
    cache = await cache_pool.get()
    if person := await cache.get(f"id:{id}"):
        return BasePerson.model_validate_json(person)

    db = await db_pool.get()

    if person := await db.query_first(sql=SELECT_BY_ID, parameters={"id": id}, model=PersonRead):
        await cache.set(f"id:{id}", person.model_dump_json())
        await cache.set(f"nick:{person.nick}", "ok")
        await db_pool.put(db)
        await cache_pool.put(cache)
        return person

    return Response(status_code=404)


@app.get("/pessoas")
async def get_pessoas_by_term(term: Optional[str] = Query(None, alias="t")):
    if not term:
        return Response(status_code=400)

    cache = await cache_pool.get()
    if term and (people := await cache.get(f"term:{term}")):
        return Response(content=people, media_type="application/json")

    db = await db_pool.get()
    resp = await db.query(sql=SELECT_BY_TERM, parameters={"term": f"%{term}%"}, model=PersonRead)
    await db_pool.put(db)
    if not resp:
        return resp

    await cache.set(f"term:{term}", TypeAdapter(list[PersonRead]).dump_json(resp))
    await cache_pool.put(cache)
    return resp


@app.get("/contagem-pessoas")
async def get_contagem_pessoas():
    db = await db_pool.get()
    await asyncio.sleep(3)
    resp = await db.query_first(sql=SELECT_COUNT)
    await db_pool.put(db)
    return resp.qty
