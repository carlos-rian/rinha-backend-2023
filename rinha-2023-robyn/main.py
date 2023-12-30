import logging
import os
from time import sleep
from uuid import UUID

from model import HTTPException, PersonWrite
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import ValidationError
from robyn import Headers, Request, Response, Robyn, jsonify

app = Robyn(__file__)

INSERT = "INSERT INTO pessoa (id, apelido, nome, nascimento, stack) VALUES (%(id)s, %(apelido)s, %(nome)s, %(nascimento)s, %(stack)s)"
SELECT_BY_ID = "SELECT id, apelido, nome, nascimento, stack FROM pessoa p WHERE p.id = %(id)s LIMIT 1"
SELECT_BY_TERM = "SELECT id, apelido, nome, nascimento, stack FROM pessoa p WHERE p.search LIKE %s LIMIT 50"
SELECT_COUNT = "SELECT count(*) FROM pessoa"


async def startup():
    logging.warning("Waiting 5 seconds to start database pool...")
    sleep(5)
    global pool
    connection_max = int(os.getenv("DATABASE_POOL_SIZE", 10))
    pool = AsyncConnectionPool(conninfo=os.environ["DATABASE_URL"], max_size=connection_max, min_size=40, max_idle=50)
    logging.warning("Database pool started!")


async def shutdown():
    logging.warning("Closing database pool...")
    await pool.close()
    logging.warning("Database pool closed!")


app.startup_handler(startup)
app.shutdown_handler(shutdown)


@app.post("/pessoas")
async def create_pessoa(request: Request):
    try:
        person = PersonWrite.model_validate_json(request.body)
        async with pool.connection() as conn:
            await conn.cursor(row_factory=dict_row).execute(INSERT, person.model_dump())
        return Response(status_code=201, headers=Headers({"location": f"/pessoas/{person.id}"}), description="OK")
    except ValidationError:
        return Response(status_code=422, headers=Headers({}), description="")
    except (HTTPException, UniqueViolation):
        return Response(status_code=400, headers=Headers({}), description="")


@app.get("/pessoas/:id")
async def get_pessoa(request: Request):
    try:
        id = request.path_params.get("id")
        UUID(id)
        async with pool.connection() as conn:
            cur = await conn.cursor(row_factory=dict_row).execute(SELECT_BY_ID, {"id": id})
            if person := await cur.fetchone():
                return jsonify(person)
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
    async with pool.connection() as conn:
        cur = await conn.cursor().execute(SELECT_COUNT)
        count = (await cur.fetchone())[0]
    return count


app.start(host=os.getenv("ROBYN_HOST", "127.0.0.1"), port=os.getenv("ROBYN_PORT", 80))
