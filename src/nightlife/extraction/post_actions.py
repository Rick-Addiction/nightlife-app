# src/nightlife/extraction/post_actions.py
"""Contrato do interprete de posts (spec E-1 §3.1): o modelo devolve ACOES,
nao campos. Anti-alucinacao POR ACAO: quote sustenta, senao a acao (ou o
campo) cai — mesmo espirito do adjusted_confidence do contrato antigo."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator

IgnoreReason = Literal["aula", "aniversario", "institucional", "esporte",
                       "repost", "sem_evento", "outro"]
_IGNORE_REASONS = frozenset(get_args(IgnoreReason))  # derivado do Literal: sem drift


class AddEvent(BaseModel):
    type: Literal["add_event"] = "add_event"
    name: str
    date_text: str | None = None       # CRU PT-BR; quem converte e o dates_ptbr
    time_text: str | None = None
    lineup: list[str] = Field(default_factory=list)
    genre: str | None = None
    ticket_url: str | None = None
    quotes: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)


class CancelEvent(BaseModel):
    type: Literal["cancel_event"] = "cancel_event"
    event_name: str
    event_date_text: str | None = None
    quote: str | None = None           # prova textual obrigatoria pra efetivar
    confidence: float = 0.0


class UpdateEvent(BaseModel):
    type: Literal["update_event"] = "update_event"
    event_name: str
    event_date_text: str | None = None
    changes: dict[str, str] = Field(default_factory=dict)   # date_text | name | ticket_url
    quote: str | None = None
    confidence: float = 0.0


class Ignore(BaseModel):
    type: Literal["ignore"] = "ignore"
    reason: IgnoreReason = "outro"
    note: str | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def _coerce_unknown_reason(cls, v: Any) -> Any:
        # B7: reason fora do Literal (modelo alucina categoria nova) nao pode
        # derrubar a interpretacao do post inteiro com ValidationError.
        if v not in _IGNORE_REASONS:
            return "outro"
        return v


Action = Annotated[Union[AddEvent, CancelEvent, UpdateEvent, Ignore],
                   Field(discriminator="type")]


class PostInterpretation(BaseModel):
    actions: list[Action] = Field(default_factory=list)


def _adjusted(a: AddEvent, field: str) -> float:
    c = a.confidence.get(field, 0.0)
    return c if field in a.quotes else c / 2


def sanitize_actions(interp: PostInterpretation) -> PostInterpretation:
    """Gate por acao: add sem quote de nome cai inteiro; campos secundarios
    suspeitos (data/ticket) viram None mas o evento fica (data alucinada e
    pior que DATA A CONFIRMAR); cancel/update sem quote OU confianca < 0.5
    caem (nunca efetivar mudanca destrutiva por palpite)."""
    out: list[Action] = []
    for a in interp.actions:
        if isinstance(a, AddEvent):
            if _adjusted(a, "name") < 0.5:
                continue
            if a.date_text and _adjusted(a, "date_text") < 0.5:
                a = a.model_copy(update={"date_text": None})
            if a.ticket_url and _adjusted(a, "ticket_url") < 0.5:
                a = a.model_copy(update={"ticket_url": None})
            out.append(a)
        elif isinstance(a, (CancelEvent, UpdateEvent)):
            if a.quote and a.confidence >= 0.5:
                out.append(a)
        else:
            out.append(a)
    return PostInterpretation(actions=out)
