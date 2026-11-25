"""Exporta as festas de sabado 31/10 (noite de sabado: 31/10 08:00 -> 01/11 06:00 SP)
do banco pra JSON, deduplicando por (nome normalizado, hora) e enriquecendo
(preco/status do Shotgun, periodo, link de mapa, flag fora-de-SP).
Saida: sat_events.json (ASCII-safe no console)."""
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

from nightlife.db import SessionLocal
from nightlife.domain.geo_scope import is_in_metro_sp

OUT = Path(__file__).with_name("sat_events.json")
SP = ZoneInfo("America/Sao_Paulo")
SQL = text("""
select e.id, e.name, e.starts_at, e.genre, e.confidence, e.ticket_url, e.raw_fields,
       v.id as venue_id, v.name as venue, v.address, v.lat, v.lng, v.instagram, v.website,
       array_agg(distinct s.source_type) as sources
from events e
left join venues v on v.id = e.venue_id
left join event_sources s on s.event_id = e.id
where e.starts_at >= '2026-10-31 08:00-03' and e.starts_at < '2026-11-01 06:00-03'
group by e.id, v.id
order by e.starts_at, v.name
""")

_SRC_LABEL = {"ra": "RA", "ticketing": "Sympla", "shotgun": "Shotgun", "site": "Site do venue",
              "ig_post": "Instagram", "flyer": "Instagram"}
_NOISE_GENRES = {"transporte, excursões e tours", "cursos e workshops", "gastronomia"}
# nao e balada: esporte, evento infantil/familiar, aula (vistos na Sympla em 28/10)
_NOISE_NAME = re.compile(r"campeonato|futebol|\bsub ?\d{2}\b|spinning|infantil|\bkids\b|crian[cç]a|dia do sim|"
                         r"ca[cç]a aos doces|\baula\b|workshop", re.I)
_POSTPONED = re.compile(r"adiad|posterg|cancelad", re.I)


def norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\b(31[./]10|31 de outubro( de 2026)?|sabado|sab\.?|halloween)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def period_of(dt: datetime) -> str:
    h = dt.astimezone(SP).hour
    if dt.astimezone(SP).day == 1 or h >= 23:
        return "madrugada"
    return "tarde" if h < 19 else "noite"


def neighborhood_of(address: str | None) -> str | None:
    if not address:
        return None
    # "R. X, 84 - Pinheiros, São Paulo - SP, 05400" -> "Pinheiros"
    m = re.search(r" - ([^,-]+?),\s*S[aã]o Paulo", address)
    if m:
        return m.group(1).strip()
    parts = [p.strip() for p in address.split(",")]
    for p in parts[1:3]:
        if p and not re.match(r"^\d", p) and "são paulo" not in p.lower() and "sp" != p.lower():
            return p
    return None


def shotgun_extras(raw_fields) -> dict:
    try:
        raw = raw_fields.get("raw") if isinstance(raw_fields, dict) else None
        d = json.loads(raw) if isinstance(raw, str) else {}
        if isinstance(d, dict) and "lines" in d:
            return {"price": d.get("price"), "status": d.get("status"), "tags": d.get("tags") or [],
                    "venue_text": d.get("venue_text")}
    except Exception:  # noqa: BLE001
        pass
    return {}


def main() -> None:
    rows = []
    with SessionLocal() as s:
        for r in s.execute(SQL).mappings():
            rows.append(dict(r))
    groups: dict[tuple, dict] = {}
    dropped = []
    for r in rows:
        dt = r["starts_at"].astimezone(SP)
        extras = shotgun_extras(r["raw_fields"])
        genre = (r["genre"] or "").strip()
        if genre.lower() in _NOISE_GENRES:
            dropped.append((r["name"], "genero fora de nightlife")); continue
        if r["lat"] is not None and r["lng"] is not None and not is_in_metro_sp(r["lat"], r["lng"]):
            dropped.append((r["name"], "fora da metro SP")); continue
        if _NOISE_NAME.search(r["name"]):
            dropped.append((r["name"], "nao e balada (esporte/infantil/aula)")); continue
        if dt.day == 31 and dt.hour < 12:
            dropped.append((r["name"], "evento de manha")); continue
        status = extras.get("status")
        if not status and _POSTPONED.search(r["name"]):
            status = "Adiado / cancelado"
        key = (norm(r["name"]), dt.strftime("%H:%M"))
        item = {
            "id": r["id"], "name": r["name"].strip(), "time": dt.strftime("%H:%M"),
            "day": dt.strftime("%d/%m"), "sort": dt.isoformat(), "period": period_of(r["starts_at"]),
            "venue": r["venue"], "venue_id": r["venue_id"], "address": r["address"],
            "neighborhood": neighborhood_of(r["address"]) or (extras.get("venue_text") if r["venue"] is None else None),
            "lat": r["lat"], "lng": r["lng"], "instagram": r["instagram"], "website": r["website"],
            "genre": genre or None, "tags": extras.get("tags", []), "price": extras.get("price"),
            "status": status, "confidence": r["confidence"],
            "url": r["ticket_url"], "sources": sorted({_SRC_LABEL.get(x, x) for x in r["sources"] if x}),
            "links": {},
        }
        if item["url"]:
            item["links"][item["sources"][0] if item["sources"] else "fonte"] = item["url"]
        g = groups.get(key)
        if g is None:
            groups[key] = item
            continue
        # merge: prefere quem tem venue/endereco; une fontes e links
        base, other = (g, item) if g["venue"] else (item, g)
        for k in ("venue", "venue_id", "address", "neighborhood", "lat", "lng", "instagram", "website",
                  "genre", "price", "status"):
            base[k] = base[k] if base[k] not in (None, "", []) else other[k]
        base["tags"] = list(dict.fromkeys(base["tags"] + other["tags"]))
        base["sources"] = sorted(set(base["sources"]) | set(other["sources"]))
        base["links"].update(other["links"])
        base["confidence"] = max(base["confidence"], other["confidence"])
        base["merged_ids"] = sorted(set(base.get("merged_ids", [base["id"]])) | {other["id"]})
        groups[key] = base
    events = sorted(groups.values(), key=lambda e: (e["sort"], e["venue"] or "zzz"))
    for e in events:
        q = " ".join(x for x in (e["venue"], e["address"]) if x) or e["name"]
        if e["lat"] is not None and e["lng"] is not None:
            e["maps"] = f"https://www.google.com/maps/search/?api=1&query={e['lat']},{e['lng']}"
        elif e["venue"] or e["address"]:
            from urllib.parse import quote
            e["maps"] = f"https://www.google.com/maps/search/?api=1&query={quote(q + ' São Paulo')}"
        else:
            e["maps"] = None
    stats = {
        "generated_at": datetime.now(SP).isoformat(timespec="minutes"),
        "rows_db": len(rows), "events": len(events), "dropped": dropped,
        "by_source": dict(Counter(src for e in events for src in e["sources"])),
        "by_period": dict(Counter(e["period"] for e in events)),
        "with_venue": sum(1 for e in events if e["venue"]),
        "halloween": sum(1 for e in events if re.search(r"hallow|bruxa|ween|gotic|vampir|terror|panico|sangrent",
                                                        unicodedata.normalize("NFD", e["name"].lower()))),
    }
    OUT.write_text(json.dumps({"stats": stats, "events": events}, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
