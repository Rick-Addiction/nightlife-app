# src/nightlife/domain/matching.py
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# Calibrado com dados reais (2026-07-03): 26/26 pares em review eram falsos
# positivos inflados por palavras genericas de venue ("Espaco X" vs "Espaco Y").
# Tokens pos-normalizacao (sem acento).
_STOPWORDS = {
    "bar", "club", "clube", "casa", "the", "o", "a", "de", "do", "da",
    "espaco", "buffet", "eventos", "evento", "salao", "teatro",
}


@dataclass
class VenueRef:
    id: int | None
    name: str
    address: str | None = None
    lat: float | None = None
    lng: float | None = None


@dataclass
class VenueMatch:
    venue: VenueRef
    score: float  # 0..1


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    tokens = [tok for tok in s.split() if tok not in _STOPWORDS]
    # nome composto so de stopwords ("A Casa", "O Bar"): usa a forma sem filtro,
    # senao o venue nunca casaria consigo mesmo e duplicaria a cada ingest
    return " ".join(tokens) if tokens else s


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na and not nb:
        # ambos reduziram a vazio (so stopwords) -> tratar como dissimilares
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def match_venue(candidate: VenueRef, existing: list[VenueRef], *, threshold: float = 0.82) -> VenueMatch | None:
    best: VenueMatch | None = None
    for e in existing:
        s = name_similarity(candidate.name, e.name)
        if None not in (candidate.lat, candidate.lng, e.lat, e.lng):
            if _haversine_km(candidate.lat, candidate.lng, e.lat, e.lng) <= 0.15:
                s = min(1.0, s + 0.1)
        if best is None or s > best.score:
            best = VenueMatch(e, s)
    if best is not None and best.score >= threshold:
        return best
    return None


VENUE_MERGE_THRESHOLD = 0.85
VENUE_REVIEW_THRESHOLD = 0.70
# Duplicata FISICA de venue nao pode estar longe de si mesma. Calibrado com
# dados reais: todos os 26 falsos positivos estavam a >0.8km; os 5 auto-merges
# corretos, a <150m (boost geo). 1km cobre variancia de geocoding com folga.
MAX_DUPLICATE_DISTANCE_KM = 1.0


def geo_distance_km(a: VenueRef, b: VenueRef) -> float | None:
    """Distancia entre dois venues, ou None se algum nao tem coordenada."""
    if None in (a.lat, a.lng, b.lat, b.lng):
        return None
    return _haversine_km(a.lat, a.lng, b.lat, b.lng)


def classify_venue_match(score: float, *, distance_km: float | None = None) -> str:
    """Faixas de decisao para upsert de venue: merge automatico so em alta
    confianca E com geo que confirme o lugar fisico. Sem geo (distance_km=None)
    nao da pra distinguir 'Mono Club' de 'Club Mono' -> nunca auto_merge."""
    if distance_km is not None and distance_km > MAX_DUPLICATE_DISTANCE_KM:
        return "distinct"                 # longe demais = lugares diferentes
    if distance_km is None:               # sem geo: sem confirmacao fisica
        return "review" if score >= VENUE_REVIEW_THRESHOLD else "distinct"
    if score >= VENUE_MERGE_THRESHOLD:
        return "auto_merge"
    if score >= VENUE_REVIEW_THRESHOLD:
        return "review"
    return "distinct"
