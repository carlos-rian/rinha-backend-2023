from datetime import date
from uuid import UUID, uuid1

from pydantic import Field, constr, field_serializer, field_validator
from pysqlx_engine import BaseRow

TypeStack = constr(max_length=32)


class HTTPException(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


class BasePerson(BaseRow):
    model_config = {"populate_by_name": True, "from_attributes": True, "extra": "ignore"}
    id: UUID = Field(default_factory=uuid1)
    apelido: str = Field(..., max_length=32)
    nome: str = Field(..., max_length=100)
    nascimento: date
    stack: list[TypeStack] | None

    @property
    def stack_str(self):
        if self.stack is None:
            return "NULL"

        stack = f" ".join(self.stack)
        return f"'{stack}'"


class PersonWrite(BasePerson):
    @field_validator("stack", mode="before")
    def validate_stack(cls, v: None | list[TypeStack]):
        if v is None:
            return v
        elif isinstance(v, list) and not all(isinstance(i, str) for i in v):
            raise HTTPException(status_code=400)
        return v

    @field_validator("nome", "apelido", mode="before")
    def validate_name_and_nick(cls, v: str):
        if isinstance(v, str):
            return v
        raise HTTPException(status_code=400)

    @field_serializer("stack")
    def ser_stack(self, stack: list[TypeStack] | None):
        return " ".join(stack) if stack else None


class PersonRead(BasePerson):
    @field_validator("stack", mode="before")
    def validate_stack(cls, v: None | str):
        return v.split(" ") if v else None
