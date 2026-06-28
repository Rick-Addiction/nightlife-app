# src/nightlife/domain/dedupe.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .matching import name_similarity, normalize_name

# Cap aplicado quando nao ha proximidade de data. Precisa ficar ABAIXO do
# limiar de "review" (0.65) em classify(), para recorrencias (mesma festa em
# datas distantes) nunca virarem candidatas a merge/review.
_RECURRENCE_CAP = 0.6


@dataclass
class EventKey:
    name: str
    starts_at: datetime | None
    venue_name: str | None = None
    organizer: str | None = None
    ticket_url: str | None = None


@dataclass
class DedupeResult:
    score: float
    decision: str  # "auto_merge" | "review" | "distinct"


def _date_proximity(a: datetime | None, b: datetime | None) -> float:
    if a is None or b is None:
        return 0.0
    diff = abs((a - b).total_seconds())
    if diff <= 3600:
        return 1.0
    if diff <= 6 * 3600:
        return 0.7
    if diff <= 24 * 3600:
        return 0.4
    return 0.0


def dedupe_score(a: EventKey, b: EventKey) -> float:
    name = name_similarity(a.name, b.name)
    date_prox = _date_proximity(a.starts_at, b.starts_at)
    if a.venue_name and b.venue_name:
        venue = name_similarity(a.venue_name, b.venue_name)
    else:
        venue = 0.0
    same_ticket = bool(a.ticket_url and b.ticket_url and a.ticket_url == b.ticket_url)

    score = 0.5 * name + 0.3 * date_prox + 0.2 * venue
    # Sem proximidade de data (e sem ticket igual), no maximo "distinto":
    # evita tratar recorrencias (mesma festa em datas distantes) como duplicata.
    if date_prox == 0.0 and not same_ticket:
        score = min(score, _RECURRENCE_CAP)
    if same_ticket:
        score = max(score, 0.95)
    if a.organizer and b.organizer and normalize_name(a.organizer) == normalize_name(b.organizer):
        score = min(1.0, score + 0.1)
    return score


def classify(score: float) -> str:
    if score >= 0.9:
        return "auto_merge"
    if score >= 0.65:
        return "review"
    return "distinct"


def compare(a: EventKey, b: EventKey) -> DedupeResult:
    s = dedupe_score(a, b)
    return DedupeResult(s, classify(s))
