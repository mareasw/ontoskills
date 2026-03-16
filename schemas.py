from pydantic import BaseModel
from typing import Literal


class Requirement(BaseModel):
    type: Literal["EnvVar", "Tool", "Hardware", "API", "Knowledge"]
    value: str
    optional: bool = False


class ExecutionPayload(BaseModel):
    executor: Literal["shell", "python", "node", "claude_tool"]
    code: str
    timeout: int | None = None


class ExtractedSkill(BaseModel):
    id: str
    hash: str
    nature: str
    genus: str
    differentia: str
    intents: list[str]
    requirements: list[Requirement]
    depends_on: list[str] = []
    extends: list[str] = []
    contradicts: list[str] = []
    constraints: list[str]
    execution_payload: ExecutionPayload | None
    provenance: str | None
