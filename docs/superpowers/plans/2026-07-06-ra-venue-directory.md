# Diretório de venues do RA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Semear os ~684 venues de nightlife de SP do diretório do RA (incl. D-EDGE) no banco, via `RASource.venues()`, para os clubes existirem mesmo sem evento futuro.

**Architecture:** Spec: `docs/superpowers/specs/2026-07-06-ra-venue-directory-design.md`. `parse_ra_venues` é PURO (fixture do shape real). `RASource.venues()` (hoje `[]`) passa a buscar `venues(areaId:400, orderBy:ALPHABETICAL, limit:20)` — o **quirk do RA** (limit≤20 traz os 684; ≥50 retorna 0). O `ingest_ra` diário já chama `venues()` → semeia diretório + eventos. Reusa `run_ingestion`.

**Tech Stack:** Python 3.14, httpx + truststore, SQLAlchemy 2.0, pytest. RA GraphQL `ra.co/graphql`, SP=area 400.

**Convenções:**
- **cwd do shell RESETA entre chamadas Bash** — comece cada comando com `cd /d/MyProjects/nightlife-app && ...`.
- Python: `.venv/Scripts/python`. Testes: `.venv/Scripts/python -m pytest ... --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife` (SEMPRE; confie no exit code — a linha "N passed" some no pipe).
- Suíte backend hoje = **158**. Commits com trailer `Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF`. **NÃO** mexa em `web/`.

---

## File Structure

```
src/nightlife/ingestion/ra_source.py   # MODIFICA — + parse_ra_venues + RASource.venues()
tests/test_ra_source.py                # MODIFICA — + testes
```

## Contexto de código (já existe em `ra_source.py`)

- `RawVenue(name, source_type, lat=None, lng=None, address=None, category=None, source_url=None, raw_payload="")` (de `.base`).
- Constantes: `RA_ENDPOINT`, `SP_AREA_ID=400`, `_USER_AGENT`, `_QUERY` (a de eventos). `import httpx` no topo.
- `class RASource`: `__init__(..., area_id=SP_AREA_ID, timeout=40.0)`, `venues()` que HOJE retorna `[]`, `events()` que pagina.
- `_venue_of(v)` (do RA-de-eventos): monta RawVenue de um venue, com heurística TBA (`name.upper().startswith("TBA")`).
- Shape real de `venues`: `{"data": {"venues": [{"id","name","address","contentUrl":"/clubs/ID","eventCountThisYear","isClosed"}, ...]}}`.

---

## Task 1: `parse_ra_venues` (puro)

**Files:** Modify `src/nightlife/ingestion/ra_source.py`; append em `tests/test_ra_source.py`

- [ ] **Step 1: Teste que falha** — em `tests/test_ra_source.py`, ADICIONE ao final:

```python
from nightlife.ingestion.ra_source import parse_ra_venues

RA_VENUES = {"data": {"venues": [
    {"id": "4973", "name": "D-EDGE", "address": "Alameda Olga, 170",
     "contentUrl": "/clubs/4973", "eventCountThisYear": 12, "isClosed": False},
    {"id": "1", "name": "Fechado", "address": "X",
     "contentUrl": "/clubs/1", "eventCountThisYear": 0, "isClosed": True},   # fechado -> fora
    {"id": "2", "name": "TBA - Rua Y", "address": None,
     "contentUrl": None, "eventCountThisYear": 0, "isClosed": False},        # TBA -> fora
    {"id": "3", "name": "", "address": None,
     "contentUrl": "/clubs/3", "eventCountThisYear": 0, "isClosed": False},  # sem nome -> fora
]}}


def test_parse_ra_venues():
    vs = parse_ra_venues(RA_VENUES)
    assert [v.name for v in vs] == ["D-EDGE"]   # fechado/TBA/vazio descartados
    d = vs[0]
    assert d.source_type == "ra"
    assert d.category == "nightclub"
    assert d.lat is None and d.lng is None       # RA nao da geo
    assert d.address == "Alameda Olga, 170"
    assert d.source_url == "https://ra.co/clubs/4973"


def test_parse_ra_venues_vazio():
    assert parse_ra_venues({}) == []
    assert parse_ra_venues({"data": {"venues": None}}) == []
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ra_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `parse_ra_venues` não existe.

- [ ] **Step 3: Implementar** — em `src/nightlife/ingestion/ra_source.py`, ADICIONE (perto do `_venue_of`, antes da classe `RASource`):

```python
def parse_ra_venues(data: dict) -> list[RawVenue]:
    """Resultado da query `venues` do RA -> RawVenues (diretorio). Puro.
    Descarta fechados, TBA e sem-nome. RA nao da geo (lat/lng None)."""
    out: list[RawVenue] = []
    for v in (data.get("data") or {}).get("venues") or []:
        if v.get("isClosed"):
            continue
        name = (v.get("name") or "").strip()
        if not name or name.upper().startswith("TBA"):
            continue
        content = v.get("contentUrl")
        out.append(RawVenue(
            name=name,
            source_type="ra",
            lat=None, lng=None,
            address=(v.get("address") or "").strip() or None,
            category="nightclub",
            source_url=f"https://ra.co{content}" if content else None,
        ))
    return out
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ra_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (todos os anteriores + 2 novos).

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/ra_source.py tests/test_ra_source.py && git commit -m "feat(ra): parse_ra_venues — diretorio de venues do RA -> RawVenues (puro)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 2: `RASource.venues()` busca o diretório

**Files:** Modify `src/nightlife/ingestion/ra_source.py`; append em `tests/test_ra_source.py`

- [ ] **Step 1: Teste que falha** — em `tests/test_ra_source.py`, ADICIONE ao final (o `from nightlife.ingestion import ra_source` já foi importado por um teste anterior; se não, adicione):

```python
def test_ra_source_venues_busca_diretorio(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"data": {"venues": [
                {"id": "4973", "name": "D-EDGE", "address": "Alameda Olga, 170",
                 "contentUrl": "/clubs/4973", "isClosed": False}]}}

    def fake_post(url, **kw):
        captured.update(kw["json"]["variables"])
        return _Resp()

    monkeypatch.setattr(ra_source.httpx, "post", fake_post)
    src = ra_source.RASource()
    vs = src.venues()
    assert captured["o"] == "ALPHABETICAL"
    assert captured["l"] == 20              # quirk do RA: limit<=20 traz os 684
    assert captured["a"] == 400             # SP
    assert [v.name for v in vs] == ["D-EDGE"]
```

- [ ] **Step 2: Ver falhar**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ra_source.py::test_ra_source_venues_busca_diretorio -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: FAIL — `venues()` retorna `[]` (não bate no RA; `captured` fica vazio → KeyError/assert falha).

- [ ] **Step 3: Implementar** — em `src/nightlife/ingestion/ra_source.py`:

Adicione a constante da query do diretório perto de `_QUERY` (a de eventos):
```python
_VENUE_DIR_LIMIT = 20  # QUIRK do RA: limit<=20 retorna os 684 de SP; limit>=50 retorna 0
_VENUES_QUERY = """query($a: ID, $o: OrderByType!, $l: Int) {
  venues(areaId: $a, orderBy: $o, limit: $l, closed: false) {
    id name address contentUrl eventCountThisYear isClosed
  }
}"""
```

E SUBSTITUA o método `venues()` da classe `RASource` (hoje `return []`) por:
```python
    def venues(self) -> list[RawVenue]:
        resp = httpx.post(
            self._endpoint,
            json={"query": _VENUES_QUERY, "variables": {
                "a": self._area_id, "o": "ALPHABETICAL", "l": _VENUE_DIR_LIMIT}},
            headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json",
                     "Referer": "https://ra.co/"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return parse_ra_venues(resp.json())
```

- [ ] **Step 4: Ver passar + commit**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m pytest tests/test_ra_source.py -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife`
Expected: PASS (todos).
Rode a suíte inteira (reporte total; zero regressão): `.venv/Scripts/python -m pytest -q --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife; echo "exit: $?"`.

```bash
cd /d/MyProjects/nightlife-app && git add src/nightlife/ingestion/ra_source.py tests/test_ra_source.py && git commit -m "feat(ra): RASource.venues() busca o diretorio de SP (ALPHABETICAL, limit:20)

Claude-Session: https://claude.ai/code/session_01TsbrWW4FNP96ER2Rb3onYF"
```

---

## Task 3: Suíte + smoke real (D-EDGE no banco)

**Files:** nenhum de produção novo.

- [ ] **Step 1: Suíte inteira verde**

Run: `cd /d/MyProjects/nightlife-app && docker compose up -d --wait && .venv/Scripts/python -m pytest --basetemp=/c/Users/henri/AppData/Local/Temp/pytest-nightlife -p no:cacheprovider; echo "exit: $?"`
Expected: `exit: 0` (158 + 3 novos = 161).

- [ ] **Step 2: Smoke real — `ingest_ra` traz o diretório + eventos**

Run: `cd /d/MyProjects/nightlife-app && .venv/Scripts/python -m nightlife.ingest_ra`
Expected: `found` bem maior que antes (diretório ~684 + eventos), `status=finished`. Cole a saída. (Pode levar ~1min pelos 684 upserts.)

- [ ] **Step 3: Confirmar D-EDGE & cia. no banco**

Run:
```bash
cd /d/MyProjects/nightlife-app && .venv/Scripts/python -c "
from nightlife.db import SessionLocal
from nightlife.models import Venue
from sqlalchemy import select, func
with SessionLocal() as s:
    print('total venues:', s.scalar(select(func.count()).select_from(Venue)))
    for t in ['d-edge','blitz','mono','casa da luz']:
        hits = s.scalars(select(Venue.name).where(Venue.name.ilike(f'%{t}%'))).all()
        print(f'  {t!r}:', hits or 'nao')
"
```
Expected: total de venues subiu bastante (centenas); `d-edge` aparece. Cole a saída.

- [ ] **Step 4:** (sem commit obrigatório — verificação.)

---

## Coverage map (plano ↔ spec)

| Requisito do spec | Onde |
|---|---|
| §4 `parse_ra_venues` puro (normal, closed, TBA, vazio) | Task 1 |
| §4 `RASource.venues()` busca o diretório (ALPHABETICAL, limit:20) | Task 2 |
| §7 suíte verde + smoke real (D-EDGE no banco) | Task 3 |

**Fora deste plano (spec §8):** Google Places/geo, UI pinar venues, runner separado, corrigir dedup geoless no core.
