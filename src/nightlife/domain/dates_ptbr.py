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
# Monday=0 ... Sunday=6
DIAS = {
    "segunda": 0, "seg": 0, "terca": 1, "terça": 1, "ter": 1, "quarta": 2, "qua": 2,
    "quinta": 3, "qui": 3, "sexta": 4, "sex": 4, "sabado": 5, "sábado": 5, "sab": 5, "sáb": 5,
    "domingo": 6, "dom": 6,
}
_DIAS_COMPLETOS = {w: d for w, d in DIAS.items() if len(w) > 3}
# abreviacoes colidem com palavras comuns ("vai ter", "dom Pedro"): so valem
# quando escritas em MAIUSCULAS no texto original ("SEX 13/06")
_DIAS_ABREV = {w: d for w, d in DIAS.items() if len(w) <= 3}


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
    # forma "22h" / "22h30" / "22hs": o 'h' e inequivoco em PT-BR
    m = re.search(r"\b(\d{1,2})\s*hs?\s*(\d{2})?\b", text)
    if m is None:
        # forma "22:30": exige minutos, senao rotulos como "Lote 2:" viram hora
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
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

    # dd/mm[/yyyy] — tokens invalidos (precos "20/40", idiomatico "24/7") sao
    # pulados em vez de abortar: uma data valida mais adiante ainda conta
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t):
        day, mon = int(m.group(1)), int(m.group(2))
        if (day, mon) == (24, 7) and not m.group(3):
            continue  # "24/7" = sempre aberto, nao uma data
        if m.group(3):
            yr = int(m.group(3))
            yr = yr + 2000 if yr < 100 else yr
            ambiguous = False
        else:
            yr, ambiguous = reference.year, True
        try:
            d = date(yr, mon, day)
            if ambiguous and d < reference:
                d = date(yr + 1, mon, day)  # rollover tambem pode falhar (29/02)
        except ValueError:
            continue
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
            if ambiguous and d < reference:
                d = date(yr + 1, mon, day)  # rollover tambem pode falhar (29/02)
        except ValueError:
            continue
        return ParsedDate(_apply_time(d, hour, minute, tzinfo), ambiguous, m.group(0))

    # dia da semana -> proxima ocorrencia >= reference.
    # nomes completos: o match mais a esquerda vence (nao a ordem do dict);
    # abreviacoes: apenas se MAIUSCULAS no texto original.
    orig = text.strip()
    best: tuple[int, str, int] | None = None  # (posicao, palavra, weekday)
    for word, wd in _DIAS_COMPLETOS.items():
        m = re.search(rf"\b{word}\b", t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), word, wd)
    if best is None:
        for word, wd in _DIAS_ABREV.items():
            for m in re.finditer(rf"\b{word}\b", t):
                if orig[m.start():m.end()].isupper() and (best is None or m.start() < best[0]):
                    best = (m.start(), word, wd)
    if best is not None:
        _, word, wd = best
        delta = (wd - reference.weekday()) % 7
        d = reference + timedelta(days=delta)
        return ParsedDate(_apply_time(d, hour, minute, tzinfo), False, word)

    return ParsedDate(None, False, None)
