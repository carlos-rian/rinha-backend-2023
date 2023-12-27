FROM python:3.12.1 as build

WORKDIR /src

COPY pyproject.toml poetry.lock ./

RUN pip install poetry

RUN poetry export -f requirements.txt > requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app/ app/
COPY entrypoint.sh ./

CMD ["sh", "entrypoint.sh"]