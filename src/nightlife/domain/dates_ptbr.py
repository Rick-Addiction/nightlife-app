# src/nightlife/domain/dates_ptbr.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MESES = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "marco": 3, "março": 3, "mar": 3,
    "abril": 4, "abr": 4, "maio": 5, "mai": 5, "junho": 6, "jun": 6, "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8, "setembro": 9, "set": 9, "outubro": 10, "out": 10,
    "novembro": 11, "nov": 11, "dezembro": 12, "dez": 12,
}
# Monday=0 ... Sunday=6 (mais longos antes dos curtos para o regex casar certo)
DIAS = {
    "segunda": 0, "seg": 0, "terca": 1, "terça": 1, "ter": 1, "quarta": 2, "qua": 2,
    "quinta": 3, "qui": 3, "sexta": 4, "sex": 4, "sabado": 5, "sábado": 5, "sab": 5, "sáb": 5,
    "domingo": 6, "dom": 6,
}


@dataclass
class ParsedDate:
    dt: datetime | None        # tz-aware (America/Sao_Paulo) ou None
    ambiguous: bool            # True quando o ano foi inferido
    matched: str | None        # trecho reconhecido


def _norm(s: str) -> str:
    return s.strip().lower()


def _apply_time(d: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)


def _extract_time(text: str) -> tuple[int, int]:
    m = re.search(r"(\d{1,2})\s*(?:h|:)\s*(\d{2})?", text)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    return 0, 0


def parse_ptbr_datetime(text: str, *, reference: date, tz: str = "America/Sao_Paulo") -> ParsedDate:
    if not text or not text.strip():
        return ParsedDate(None, False, None)
    tzinfo = ZoneInfo(tz)
    t = _norm(text)
    hour, minute = _extract_time(t)

    if re.search(r"\bhoje\b", t):
        return ParsedDate(_apply_time(reference, hour, minute, tzinfo), False, "hoje")
    if re.search(r"\b(amanha|amanhã)\b", t):
        return ParsedDate(_apply_time(reference + timedelta(days=1), hour, minute, tzinfo), False, "amanhã")

    # dd/mm[/yyyy]
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        if m.group(3):
            yr = int(m.group(3))
            yr = yr + 2000 if yr < 100 else yr
            ambiguous = False
        else:
            yr, ambiguous = reference.year, True
        try:
            d = date(yr, mon, day)
        except ValueError:
            return ParsedDate(None, False, None)
        if ambiguous and d < reference:
            d = date(yr + 1, mon, day)
        return ParsedDate(_apply_time(d, hour, minute, tzinfo), ambiguous, m.group(0))

    # "13 [de] junho [de 2026]" / "13 jun"
    for m in re.finditer(r"\b(\d{1,2})\s+(?:de\s+)?([a-zç]{3,})(?:\s+de\s+(\d{4}))?\b", t):
        mon_word = _norm(m.group(2))
        if mon_word not in MESES:
            continue
        day, mon = int(m.group(1)), MESES[mon_word]
        if m.group(3):
            yr, ambiguous = int(m.group(3)), False
        else:
            yr, ambiguous = reference.year, True
        try:
            d = date(yr, mon, day)
        except ValueError:
            return ParsedDate(None, False, None)
        if ambiguous and d < reference:
            d = date(yr + 1, mon, day)
        return ParsedDate(_apply_time(d, hour, minute, tzinfo), ambiguous, m.group(0))

    # dia da semana -> proxima ocorrencia >= reference
    for word, wd in DIAS.items():
        if re.search(rf"\b{word}\b", t):
            delta = (wd - reference.weekday()) % 7
            d = reference + timedelta(days=delta)
            return ParsedDate(_apply_time(d, hour, minute, tzinfo), False, word)

    return ParsedDate(None, False, None)
