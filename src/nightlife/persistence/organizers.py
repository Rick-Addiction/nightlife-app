# src/nightlife/persistence/organizers.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.matching import normalize_name
from ..models import Organizer


def get_or_create_organizer(session: Session, name: str) -> Organizer:
    """Organizer e cidadao de primeira classe: reusa por nome normalizado
    (mesmo padrao O(n) do esqueleto), cria se nao existe."""
    wanted = normalize_name(name)
    for org in session.scalars(select(Organizer)).all():
        if normalize_name(org.name) == wanted:
            return org
    org = Organizer(name=name)
    session.add(org)
    session.flush()
    return org
