import logging
import os
from contextlib import asynccontextmanager
from time import sleep
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, Query, Response
from fastapi.responses import Response
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from model import PersonWrite

INSERT = "INSERT INTO pessoa (id, apelido, nome, nascimento, stack) VALUES (%(id)s, %(apelido)s, %(nome)s, %(nascimento)s, %(stack)s)"
SELECT_BY_ID = "SELECT id, apelido, nome, nascimento, stack FROM pessoa p WHERE p.id = %(id)s LIMIT 1"
SELECT_BY_TERM = "SELECT id, apelido, nome, nascimento, stack FROM pessoa p WHERE p.search LIKE %s LIMIT 50"
SELECT_COUNT = "SELECT count(*) FROM pessoa"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.warning("Waiting 5 seconds to start database pool...")
    sleep(5)
    global pool
    connection_max = int(os.getenv("DATABASE_POOL_SIZE", 10))
    pool = AsyncConnectionPool(
        conninfo=os.environ["DATABASE_URL"],
        max_size=connection_max,
        min_size=int(connection_max / 2),
        max_idle=int(connection_max / 3),
    )
    logging.warning("Database pool started!")
    yield
    logging.warning("Waiting 5 seconds to close database pool...")
    await pool.close()


app = FastAPI(lifespan=lifespan)


@app.post("/pessoas", status_code=201)
async def post_pessoa(person: PersonWrite, response: Response):
    try:
        async with pool.connection() as conn:
            await conn.cursor(row_factory=dict_row).execute(INSERT, person.model_dump())
    except UniqueViolation:
        return Response(status_code=400)

    response.headers["Location"] = f"/pessoas/{person.id}"
    response.status_code = 201
    return response


@app.get("/pessoas/{id}")
async def get_pessoa_by_id(id: UUID):
    async with pool.connection() as conn:
        cur = await conn.cursor(row_factory=dict_row).execute(SELECT_BY_ID, {"id": str(id)})
        if person := await cur.fetchone():
            return person

    return Response(status_code=404)


@app.get("/pessoas")
async def get_pessoas_by_term(term: Optional[str] = Query(None, alias="t")):
    if term:
        async with pool.connection() as conn:
            cur = await conn.cursor(row_factory=dict_row).execute(SELECT_BY_TERM, (f"%{term}%",))
            people = await cur.fetchall()
            return people

    return Response(status_code=400)


@app.get("/contagem-pessoas")
async def get_contagem_pessoas():
    async with pool.connection() as conn:
        cur = await conn.cursor().execute(SELECT_COUNT)
        count = (await cur.fetchone())[0]

    return count
