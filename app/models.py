from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class Query(BaseModel):
    user_query: str = Field(min_length=1, max_length=4000)
    document_ids: list[UUID] = Field(min_length=1, max_length=5)
    thread_id: UUID | None = None

    @field_validator("user_query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Question cannot be blank")
        return value.strip()


class Section(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    number: str = Field(min_length=1, max_length=100)
    title: str = Field(default="", max_length=1000)
    parent_id: str | None = None
    kind: Literal["chapter", "section", "table", "equation", "diagram"] = "section"
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    references: list[str] = Field(default_factory=list)


class Document(BaseModel):
    id: UUID
    title: str = Field(min_length=1)
    edition: str
    source_uri: str = ""
    sections: list[Section] = Field(min_length=1)

    @field_validator("sections")
    @classmethod
    def valid_links(cls, sections):
        by_id = {s.id: s for s in sections}
        if len(by_id) != len(sections):
            raise ValueError("Section IDs must be unique within a document")
        for section in sections:
            if any(ref not in by_id for ref in section.references):
                raise ValueError("Reference points to an unknown section")
            seen = {section.id}
            parent = section.parent_id
            while parent is not None:
                if parent not in by_id or parent in seen:
                    raise ValueError("Section hierarchy contains a missing parent or cycle")
                seen.add(parent)
                parent = by_id[parent].parent_id
        return sections
