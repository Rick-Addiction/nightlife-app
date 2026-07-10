# Ciclo C — Plano C-1: Fundação + Festas + Flyer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O esqueleto do redesign Rave Brutalista no ar: 3 abas navegáveis (mobile bottom-tabs / desktop 40-60), aba FESTAS como feed "Esta Noite" com **flyer do Instagram** (hero + thumbs), detalhe da festa com ações, e o backend servindo os flyers (`/flyers` + `EventOut.flyer_url`).

**Architecture:** Rebuild-in-place da camada de UI (spec `2026-07-10-frontend-redesign-design.md`, §4 Plano C-1). Mantém: `api/client`, `data/join`, `map/geojson`, `MapView` (rebrandado). Substitui: `theme.css`, `App.tsx`, `FilterBar`→`FilterChips`, `EventList/EventCard`→`components/EventCard`+`tabs/FestasTab`. Novo: `BottomTabs`, `EventDetail`, preset `tomorrow`. Backend: static mount + `flyer_url` (derivado do permalink IG → arquivo em `flyers/processed/`).

**Tech Stack:** React 19 + Vite + TS, react-map-gl/maplibre, Vitest + Testing Library; FastAPI + pytest.

**Referências verificadas do código atual:**
- `filters/state.ts`: `Preset = 'upcoming'|'today'|'weekend'|'all'`; `FilterState {preset, genre, minConfidence, includePast}`; `filterReducer`; `queryFromFilters(f, now)` usa `isoDate` LOCAL (não UTC).
- `data/join.ts`: `EventWithGeo extends EventOut { venueName, lat, lng, mappable }`.
- `api/types.ts`: `EventOut { id, name, starts_at, ends_at, venue_id, status, genre, ticket_url, confidence, effective_confidence }`; `VenueOut` (com instagram/website).
- `api/main.py`: `list_events`/`get_event` retornam `EventOut` via `_with_effective`; `EventSource(source_url)` carrega o permalink IG (`instagram.com/p/{shortcode}/`) dos eventos de flyer.
- Flyers: `flyers/processed/{shortcode}.{jpg|jpeg|png|webp}` (persistidos; sidecars .json ao lado).
- `web/src/App.tsx`: fetch único `Promise.all([fetchEvents(queryFromFilters(filters)), fetchVenues()])`; estados `venues/showVenues` (mantidos p/ MapView).
- `MapView.tsx`: props `{events, venues, selectedId, onSelect, showVenues}`; markers DOM de evento + camada GL `venue-dots`/`venue-sel`.
- Testes web com `render/screen/userEvent` (ver `FilterBar.test.tsx`); `npx vitest run <arquivo>` de `web/`; `npx tsc -b --noEmit`.

**Convenção de commit:** trailer `Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu`.
**Backend tests:** `.venv/Scripts/python -m pytest <arquivo> -v` (Postgres 5434 de pé; suíte completa com `--basetemp`).

---

### Task 1: Backend — static `/flyers` + `EventOut.flyer_url`

**Files:**
- Modify: `src/nightlife/config.py`, `src/nightlife/api/schemas.py`, `src/nightlife/api/main.py`
- Test: `tests/test_api_flyers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_flyers.py
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from nightlife import config
from nightlife.api.deps import get_session
from nightlife.api.main import app
from nightlife.models import Event, EventSource, Venue

SP = ZoneInfo("America/Sao_Paulo")


def _client(session):
    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    return TestClient(app)


def _event_with_permalink(session, shortcode):
    v = Venue(name="Selva Club", lat=-23.55, lng=-46.65)
    session.add(v)
    session.flush()
    e = Event(name="Mamba Negra", venue_id=v.id, status="scheduled", confidence=50,
              starts_at=datetime(2099, 7, 12, 23, 0, tzinfo=SP))
    session.add(e)
    session.flush()
    session.add(EventSource(event_id=e.id, source_type="vision_flyer",
                            source_url=f"https://www.instagram.com/p/{shortcode}/"))
    session.flush()
    return e


def test_flyer_url_quando_arquivo_existe(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FLYERS_PROCESSED_DIR", tmp_path)
    (tmp_path / "ABC12345678.jpg").write_bytes(b"x")
    e = _event_with_permalink(session, "ABC12345678")
    client = _client(session)
    try:
        row = next(x for x in client.get("/events").json() if x["id"] == e.id)
        assert row["flyer_url"] == "/flyers/ABC12345678.jpg"
        one = client.get(f"/events/{e.id}").json()
        assert one["flyer_url"] == "/flyers/ABC12345678.jpg"
    finally:
        app.dependency_overrides.clear()


def test_flyer_url_extensao_variada_e_ausencia(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FLYERS_PROCESSED_DIR", tmp_path)
    (tmp_path / "WEBP1234567.webp").write_bytes(b"x")
    com = _event_with_permalink(session, "WEBP1234567")
    sem = _event_with_permalink(session, "NAOEXISTE11")
    client = _client(session)
    try:
        rows = {x["id"]: x for x in client.get("/events").json()}
        assert rows[com.id]["flyer_url"] == "/flyers/WEBP1234567.webp"
        assert rows[sem.id]["flyer_url"] is None
    finally:
        app.dependency_overrides.clear()


def test_evento_sem_source_ig_tem_flyer_null(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FLYERS_PROCESSED_DIR", tmp_path)
    v = Venue(name="X")
    session.add(v)
    session.flush()
    e = Event(name="Sem IG", venue_id=v.id, status="scheduled", confidence=10,
              starts_at=datetime(2099, 1, 1, 23, 0, tzinfo=SP))
    session.add(e)
    session.flush()
    client = _client(session)
    try:
        row = next(x for x in client.get("/events").json() if x["id"] == e.id)
        assert row["flyer_url"] is None
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_api_flyers.py -v`
Expected: FAIL (`AttributeError: module 'nightlife.config' has no attribute 'FLYERS_PROCESSED_DIR'` e/ou `KeyError: 'flyer_url'`).

- [ ] **Step 3: Write minimal implementation**

`config.py` — adicionar ao fim (o `Path` já é importado):

```python
# Flyers processados (Ciclo B) servidos pela API em /flyers (Ciclo C)
FLYERS_PROCESSED_DIR = Path(os.environ.get("FLYERS_DIR", "flyers")) / "processed"
```

`schemas.py` — em `EventOut`, adicionar após `ticket_url`:

```python
    flyer_url: str | None = None
```

`api/main.py`:
1. Imports novos: `import re`, `from fastapi.staticfiles import StaticFiles`, `from ..models import Event, EventSource, Venue, VenueSource` (adicionar `EventSource`), `from .. import config`.
2. Após `app = FastAPI(...)`:
```python
config.FLYERS_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/flyers", StaticFiles(directory=str(config.FLYERS_PROCESSED_DIR)), name="flyers")

_IG_PERMALINK = re.compile(r"instagram\.com/p/([A-Za-z0-9_-]+)")


def _flyer_files() -> dict[str, str]:
    """{shortcode: nome do arquivo} do diretorio de flyers processados."""
    try:
        return {p.stem: p.name for p in config.FLYERS_PROCESSED_DIR.iterdir()
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}}
    except OSError:
        return {}


def _flyer_urls_for(session: Session, event_ids: list[int]) -> dict[int, str]:
    """event_id -> /flyers/arquivo, para eventos com permalink IG cujo flyer existe."""
    if not event_ids:
        return {}
    files = _flyer_files()
    if not files:
        return {}
    out: dict[int, str] = {}
    rows = session.execute(
        select(EventSource.event_id, EventSource.source_url)
        .where(EventSource.event_id.in_(event_ids), EventSource.source_url.is_not(None))
    ).all()
    for eid, url in rows:
        m = _IG_PERMALINK.search(url or "")
        if m and m.group(1) in files and eid not in out:
            out[eid] = f"/flyers/{files[m.group(1)]}"
    return out
```
3. Em `list_events`, após montar `outs` (antes do filtro de buffet), anexar:
```python
    flyers = _flyer_urls_for(session, [o.id for o in outs])
    for o in outs:
        o.flyer_url = flyers.get(o.id)
```
4. Em `get_event`, antes do `return`:
```python
    out = _with_effective(EventOut, event, datetime.now(timezone.utc))
    out.flyer_url = _flyer_urls_for(session, [event.id]).get(event.id)
    return out
```
(ajustando o return existente para usar a variável.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_api_flyers.py tests/test_api.py -v`
Expected: PASS (novos + os 12 de test_api intactos).

- [ ] **Step 5: Commit**

```bash
git add src/nightlife/config.py src/nightlife/api/schemas.py src/nightlife/api/main.py tests/test_api_flyers.py
git commit -m "feat: API serve flyers (/flyers static + EventOut.flyer_url via permalink IG)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 2: tokens do tema + tipos TS

**Files:**
- Modify: `web/src/theme.css` (REESCREVER), `web/src/api/types.ts` (EventOut ganha `flyer_url`), `web/index.html` (título/fundo)

Sem teste próprio (CSS + tipo); o `tsc` e os testes de componentes das tasks seguintes verificam. NÃO tocar componentes ainda — o visual antigo fica temporariamente "quebrado de bonito" até a Task 7 religar tudo (o merge só acontece no fim do plano).

- [ ] **Step 1: Reescrever `web/src/theme.css`**

```css
:root {
  --pink: #ff2e88; --green: #00ff85; --black: #000;
  --panel: #111; --line: #333; --text: #fff; --muted: #888; --dim: #555;
}
* { box-sizing: border-box; }
html, body, #root { height: 100%; }
body {
  margin: 0; background: var(--black); color: var(--text);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--green); text-decoration: none; }

/* tipografia brutalista */
.hline { font-weight: 900; text-transform: uppercase; letter-spacing: -0.04em; line-height: 0.95; }
.label { font-size: 10px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); }

/* chips de filtro */
.chip {
  font-size: 11px; font-weight: 800; padding: 6px 12px; cursor: pointer;
  background: var(--panel); color: var(--text); border: 1px solid var(--line);
  text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap;
}
.chip.on { background: var(--pink); color: var(--black); border-color: var(--pink); font-weight: 900; }
.chip.grn { color: var(--green); border-color: var(--green); }

/* cards de evento */
.b-card { border: 2px solid var(--line); background: var(--black); position: relative; cursor: pointer; }
.b-card.hot, .b-card.sel { border-color: var(--text); }
.b-card .conf {
  position: absolute; top: -2px; right: -2px; background: var(--green); color: var(--black);
  font-size: 10px; font-weight: 900; padding: 2px 8px;
}
.b-card .title { font-size: 16px; font-weight: 900; text-transform: uppercase; letter-spacing: -0.03em; }
.b-card .meta { font-size: 11px; color: var(--muted); font-weight: 700; margin-top: 3px; }
.tag { display: inline-block; font-size: 9px; font-weight: 800; padding: 2px 8px; background: var(--pink); color: var(--black); margin-right: 4px; text-transform: uppercase; }
.tag.ghost { background: var(--panel); color: var(--text); border: 1px solid var(--line); }

/* botoes de acao (detalhe) */
.b-btn { display: block; text-align: center; font-weight: 900; font-size: 13px; padding: 12px 0; text-transform: uppercase; cursor: pointer; border: 1px solid var(--line); background: var(--panel); color: var(--text); }
.b-btn.primary { background: var(--green); color: var(--black); border-color: var(--green); }

/* barra de abas (mobile) */
.tabbar { position: fixed; bottom: 0; left: 0; right: 0; display: flex; z-index: 30; }
.tabbar button {
  flex: 1; padding: 13px 0; font-weight: 900; font-size: 12px; letter-spacing: 0.06em;
  background: var(--panel); color: var(--text); border: none; border-top: 2px solid var(--line);
  text-transform: uppercase; cursor: pointer;
}
.tabbar button.on { background: var(--pink); color: var(--black); border-top-color: var(--pink); }

/* header desktop */
.d-header { display: flex; justify-content: space-between; align-items: center; background: var(--pink); color: var(--black); padding: 10px 18px; font-weight: 900; }
.d-header nav { display: flex; gap: 18px; font-size: 12px; text-transform: uppercase; }
.d-header nav span { cursor: pointer; opacity: 0.6; }
.d-header nav span.on { opacity: 1; border-bottom: 3px solid var(--black); }

.empty { padding: 40px; text-align: center; color: var(--muted); font-weight: 700; }
```

- [ ] **Step 2: `web/src/api/types.ts`** — em `EventOut`, adicionar após `ticket_url`:
```ts
  flyer_url: string | null
```

- [ ] **Step 3: `web/index.html`** — garantir `<title>RADAR★SP</title>` e `<meta name="theme-color" content="#000000">` no head (manter o resto).

- [ ] **Step 4: Type-check** — Run (de `web/`): `npx tsc -b --noEmit` — deve passar (o campo novo é aditivo; se algum mock de teste de `EventOut` reclamar de campo faltando, adicionar `flyer_url: null` nele — provável em `data/join.test.ts` e `data/venueEvents.test.ts`).

- [ ] **Step 5: Commit**

```bash
git add web/src/theme.css web/src/api/types.ts web/index.html web/src/data/join.test.ts web/src/data/venueEvents.test.ts
git commit -m "feat: tokens do tema brutalista + EventOut.flyer_url no TS

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 3: `components/EventCard` (hero + linha, com flyer)

**Files:**
- Create: `web/src/components/EventCard.tsx`
- Test: `web/src/components/EventCard.test.tsx`

(O `list/EventCard.tsx` antigo continua existindo até a Task 7 remover; o novo nasce em `components/`.)

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/components/EventCard.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EventCard } from './EventCard'
import type { EventWithGeo } from '../data/join'

const ev = (over: Partial<EventWithGeo>): EventWithGeo => ({
  id: 1, name: 'Mamba Negra', starts_at: '2099-07-12T23:00:00-03:00', ends_at: null,
  venue_id: 5, status: 'scheduled', genre: 'Techno', ticket_url: null, confidence: 85,
  effective_confidence: 85, flyer_url: null, venueName: 'Selva Club',
  lat: -23.55, lng: -46.65, mappable: true, ...over,
})

describe('EventCard', () => {
  it('hero mostra o flyer grande e o nome', () => {
    render(<EventCard event={ev({ flyer_url: '/flyers/ABC.jpg' })} variant="hero" onOpen={() => {}} />)
    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('src', '/flyers/ABC.jpg')
    expect(screen.getByText('Mamba Negra')).toBeInTheDocument()
    expect(screen.getByText('85')).toBeInTheDocument()
  })

  it('linha sem flyer nao renderiza img', () => {
    render(<EventCard event={ev({ flyer_url: null })} variant="row" onOpen={() => {}} />)
    expect(screen.queryByRole('img')).toBeNull()
    expect(screen.getByText(/Selva Club/)).toBeInTheDocument()
  })

  it('linha com flyer mostra thumb', () => {
    render(<EventCard event={ev({ flyer_url: '/flyers/T.jpg' })} variant="row" onOpen={() => {}} />)
    expect(screen.getByRole('img')).toHaveAttribute('src', '/flyers/T.jpg')
  })

  it('clique chama onOpen com o evento', async () => {
    const onOpen = vi.fn()
    const e = ev({})
    render(<EventCard event={e} variant="row" onOpen={onOpen} />)
    await userEvent.click(screen.getByText('Mamba Negra'))
    expect(onOpen).toHaveBeenCalledWith(e)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (de `web/`): `npx vitest run src/components/EventCard.test.tsx`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Write minimal implementation**

```tsx
// web/src/components/EventCard.tsx
import type { EventWithGeo } from '../data/join'

export function fmtDate(iso: string | null): string {
  if (!iso) return 'data a confirmar'
  const d = new Date(iso)
  return d.toLocaleString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    .toUpperCase()
}

export function EventCard({ event, variant, onOpen }: {
  event: EventWithGeo; variant: 'hero' | 'row'; onOpen: (e: EventWithGeo) => void
}) {
  const meta = `${fmtDate(event.starts_at)}${event.venueName ? ` → ${event.venueName}` : ''}`
  if (variant === 'hero') {
    return (
      <div className="b-card hot" onClick={() => onOpen(event)} style={{ margin: '8px 12px 0' }}>
        {event.flyer_url && (
          <img src={event.flyer_url} alt={event.name}
               style={{ width: '100%', height: 190, objectFit: 'cover', display: 'block',
                        borderBottom: '2px solid var(--pink)' }} />
        )}
        <div style={{ padding: 10 }}>
          <div className="title" style={{ fontSize: 19 }}>{event.name}</div>
          <div className="meta">{meta}</div>
          <div style={{ marginTop: 7 }}>
            {event.genre && <span className="tag">{event.genre}</span>}
            {event.ticket_url && <span className="tag ghost">ticket</span>}
          </div>
        </div>
        <span className="conf">{event.effective_confidence}</span>
      </div>
    )
  }
  return (
    <div className="b-card" onClick={() => onOpen(event)}
         style={{ margin: '8px 12px 0', padding: 9, display: 'flex', gap: 10, alignItems: 'center' }}>
      {event.flyer_url && (
        <img src={event.flyer_url} alt="" style={{ width: 46, height: 46, objectFit: 'cover', flex: 'none' }} />
      )}
      <div style={{ minWidth: 0 }}>
        <div className="title">{event.name}</div>
        <div className="meta">{meta}{!event.mappable && ' · LOCAL A CONFIRMAR'}</div>
      </div>
      <span className="conf">{event.effective_confidence}</span>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (de `web/`): `npx vitest run src/components/EventCard.test.tsx`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/EventCard.tsx web/src/components/EventCard.test.tsx
git commit -m "feat: EventCard brutalista (hero com flyer + linha com thumb)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 4: preset `tomorrow` + `FilterChips`

**Files:**
- Modify: `web/src/filters/state.ts`
- Create: `web/src/components/FilterChips.tsx`
- Test: `web/src/filters/state.test.ts` (adicionar) + `web/src/components/FilterChips.test.tsx`

- [ ] **Step 1: Write the failing tests**

Em `web/src/filters/state.test.ts`, adicionar ao fim (ver imports existentes no arquivo):

```ts
describe('preset tomorrow', () => {
  it('gera date_from/date_to de amanha (calendario local)', () => {
    const now = new Date(2026, 6, 10, 22, 0)   // 10/07/2026 22h local
    const q = queryFromFilters({ ...initialFilters, preset: 'tomorrow' }, now)
    expect(q.date_from).toBe('2026-07-11')
    expect(q.date_to).toBe('2026-07-11')
  })
})
```

Criar `web/src/components/FilterChips.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterChips } from './FilterChips'
import { initialFilters } from '../filters/state'

describe('FilterChips', () => {
  it('marca o preset ativo e dispara setPreset ao clicar', async () => {
    const dispatch = vi.fn()
    render(<FilterChips filters={{ ...initialFilters, preset: 'today' }} dispatch={dispatch} />)
    expect(screen.getByRole('button', { name: 'HOJE' })).toHaveClass('on')
    await userEvent.click(screen.getByRole('button', { name: 'FDS' }))
    expect(dispatch).toHaveBeenCalledWith({ type: 'setPreset', preset: 'weekend' })
  })

  it('renderiza os 5 presets', () => {
    render(<FilterChips filters={initialFilters} dispatch={() => {}} />)
    for (const label of ['PRÓXIMAS', 'HOJE', 'AMANHÃ', 'FDS', 'TUDO']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run (de `web/`): `npx vitest run src/filters/state.test.ts src/components/FilterChips.test.tsx`
Expected: FAIL (preset 'tomorrow' não tipado / módulo FilterChips não existe).

- [ ] **Step 3: Write minimal implementation**

Em `filters/state.ts`:
1. `export type Preset = 'upcoming' | 'today' | 'tomorrow' | 'weekend' | 'all'`
2. Em `queryFromFilters`, adicionar o ramo (após o de `today`):
```ts
  } else if (f.preset === 'tomorrow') {
    const t = new Date(now); t.setDate(now.getDate() + 1)
    q.date_from = isoDate(t)
    q.date_to = isoDate(t)
```

Criar `web/src/components/FilterChips.tsx`:

```tsx
import type { Dispatch } from 'react'
import type { FilterAction, FilterState, Preset } from '../filters/state'

const PRESETS: { key: Preset; label: string }[] = [
  { key: 'upcoming', label: 'PRÓXIMAS' },
  { key: 'today', label: 'HOJE' },
  { key: 'tomorrow', label: 'AMANHÃ' },
  { key: 'weekend', label: 'FDS' },
  { key: 'all', label: 'TUDO' },
]

export function FilterChips({ filters, dispatch }: {
  filters: FilterState; dispatch: Dispatch<FilterAction>
}) {
  return (
    <div style={{ display: 'flex', gap: 5, padding: '6px 12px', overflowX: 'auto' }}>
      {PRESETS.map((p) => (
        <button key={p.key} className={`chip${filters.preset === p.key ? ' on' : ''}`}
                onClick={() => dispatch({ type: 'setPreset', preset: p.key })}>
          {p.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (de `web/`): `npx vitest run src/filters/state.test.ts src/components/FilterChips.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/filters/state.ts web/src/filters/state.test.ts web/src/components/FilterChips.tsx web/src/components/FilterChips.test.tsx
git commit -m "feat: preset AMANHA + FilterChips brutalista

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 5: `tabs/FestasTab` + helper `pickHero`

**Files:**
- Create: `web/src/tabs/FestasTab.tsx`, `web/src/data/hero.ts`
- Test: `web/src/data/hero.test.ts`, `web/src/tabs/FestasTab.test.tsx`

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/data/hero.test.ts
import { describe, it, expect } from 'vitest'
import { pickHero } from './hero'
import type { EventWithGeo } from './join'

const ev = (id: number, flyer: string | null): EventWithGeo => ({
  id, name: `E${id}`, starts_at: '2099-07-12T23:00:00-03:00', ends_at: null,
  venue_id: 1, status: 'scheduled', genre: null, ticket_url: null, confidence: 50,
  effective_confidence: 50, flyer_url: flyer, venueName: null, lat: null, lng: null, mappable: false,
})

describe('pickHero', () => {
  it('primeiro evento COM flyer vira hero; resto preserva a ordem', () => {
    const { hero, rest } = pickHero([ev(1, null), ev(2, '/f/2.jpg'), ev(3, '/f/3.jpg')])
    expect(hero?.id).toBe(2)
    expect(rest.map((e) => e.id)).toEqual([1, 3])
  })
  it('sem flyers: sem hero, tudo em rest', () => {
    const { hero, rest } = pickHero([ev(1, null), ev(2, null)])
    expect(hero).toBeNull()
    expect(rest.map((e) => e.id)).toEqual([1, 2])
  })
})
```

```tsx
// web/src/tabs/FestasTab.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FestasTab } from './FestasTab'
import { initialFilters } from '../filters/state'
import type { EventWithGeo } from '../data/join'

const ev = (id: number, name: string, flyer: string | null): EventWithGeo => ({
  id, name, starts_at: '2099-07-12T23:00:00-03:00', ends_at: null,
  venue_id: 1, status: 'scheduled', genre: null, ticket_url: null, confidence: 50,
  effective_confidence: 50, flyer_url: flyer, venueName: 'Selva Club', lat: -23.5, lng: -46.6, mappable: true,
})

describe('FestasTab', () => {
  it('manchete por preset + contagem + hero destacado', () => {
    render(<FestasTab events={[ev(1, 'Mamba Negra', '/f/1.jpg'), ev(2, 'Ghost', null)]}
                      filters={{ ...initialFilters, preset: 'today' }} dispatch={() => {}}
                      onOpen={() => {}} />)
    expect(screen.getByText(/ESTA/)).toBeInTheDocument()      // manchete "ESTA NOITE"
    expect(screen.getByText(/2 FESTAS/)).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAttribute('src', '/f/1.jpg')  // hero
    expect(screen.getByText('Ghost')).toBeInTheDocument()
  })

  it('vazio mostra estado honesto', () => {
    render(<FestasTab events={[]} filters={initialFilters} dispatch={() => {}} onOpen={() => {}} />)
    expect(screen.getByText(/Nenhuma festa/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run (de `web/`): `npx vitest run src/data/hero.test.ts src/tabs/FestasTab.test.tsx`
Expected: FAIL (módulos não existem).

- [ ] **Step 3: Write minimal implementation**

```ts
// web/src/data/hero.ts
import type { EventWithGeo } from './join'

/** Primeiro evento COM flyer vira o card-heroi do feed; o resto mantem a ordem. */
export function pickHero(events: EventWithGeo[]): { hero: EventWithGeo | null; rest: EventWithGeo[] } {
  const i = events.findIndex((e) => e.flyer_url)
  if (i === -1) return { hero: null, rest: events }
  return { hero: events[i], rest: [...events.slice(0, i), ...events.slice(i + 1)] }
}
```

```tsx
// web/src/tabs/FestasTab.tsx
import type { Dispatch } from 'react'
import type { FilterAction, FilterState, Preset } from '../filters/state'
import type { EventWithGeo } from '../data/join'
import { pickHero } from '../data/hero'
import { EventCard } from '../components/EventCard'
import { FilterChips } from '../components/FilterChips'

const TITLES: Record<Preset, [string, string]> = {
  upcoming: ['PRÓXIMAS', 'FESTAS'],
  today: ['ESTA', 'NOITE'],
  tomorrow: ['AMANHÃ', 'À NOITE'],
  weekend: ['FIM DE', 'SEMANA'],
  all: ['TUDO', 'QUE HÁ'],
}

export function FestasTab({ events, filters, dispatch, onOpen }: {
  events: EventWithGeo[]; filters: FilterState
  dispatch: Dispatch<FilterAction>; onOpen: (e: EventWithGeo) => void
}) {
  const [l1, l2] = TITLES[filters.preset]
  const { hero, rest } = pickHero(events)
  return (
    <div style={{ paddingBottom: 70 }}>
      <div style={{ padding: '14px 12px 4px' }}>
        <div className="hline" style={{ fontSize: 30 }}>{l1}<br /><span style={{ color: 'var(--pink)' }}>{l2}</span></div>
        <div className="label" style={{ marginTop: 5 }}>{events.length} FESTAS</div>
      </div>
      <FilterChips filters={filters} dispatch={dispatch} />
      {events.length === 0 && <div className="empty">Nenhuma festa com esses filtros.</div>}
      {hero && <EventCard event={hero} variant="hero" onOpen={onOpen} />}
      {rest.map((e) => <EventCard key={e.id} event={e} variant="row" onOpen={onOpen} />)}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (de `web/`): `npx vitest run src/data/hero.test.ts src/tabs/FestasTab.test.tsx`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add web/src/data/hero.ts web/src/data/hero.test.ts web/src/tabs/FestasTab.tsx web/src/tabs/FestasTab.test.tsx
git commit -m "feat: FestasTab (feed Esta Noite: manchete, hero com flyer, linhas)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 6: `components/EventDetail` (sheet com ações)

**Files:**
- Modify: `web/src/data/join.ts` (carregar `venueInstagram`)
- Create: `web/src/components/EventDetail.tsx`
- Test: `web/src/components/EventDetail.test.tsx` (+ ajuste em `web/src/data/join.test.ts`)

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/components/EventDetail.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EventDetail } from './EventDetail'
import type { EventWithGeo } from '../data/join'

const ev = (over: Partial<EventWithGeo>): EventWithGeo => ({
  id: 1, name: 'Mamba Negra', starts_at: '2099-07-12T23:00:00-03:00', ends_at: null,
  venue_id: 5, status: 'scheduled', genre: 'Techno', ticket_url: 'https://t/x',
  confidence: 85, effective_confidence: 85, flyer_url: '/flyers/A.jpg',
  venueName: 'Selva Club', venueInstagram: 'selva.011', lat: -23.55, lng: -46.65, mappable: true, ...over,
})

describe('EventDetail', () => {
  it('mostra flyer, info e os 3 botoes com links certos', () => {
    render(<EventDetail event={ev({})} onClose={() => {}} />)
    expect(screen.getByRole('img')).toHaveAttribute('src', '/flyers/A.jpg')
    expect(screen.getByText('Mamba Negra')).toBeInTheDocument()
    expect(screen.getByText(/Selva Club/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /TICKET/ })).toHaveAttribute('href', 'https://t/x')
    expect(screen.getByRole('link', { name: 'IG' })).toHaveAttribute('href', 'https://instagram.com/selva.011')
    expect(screen.getByRole('link', { name: 'MAPA' }))
      .toHaveAttribute('href', 'https://maps.google.com/?q=-23.55,-46.65')
  })

  it('sem ticket/ig/geo esconde os botoes correspondentes', () => {
    render(<EventDetail event={ev({ ticket_url: null, venueInstagram: null, lat: null, lng: null, mappable: false, flyer_url: null })}
                        onClose={() => {}} />)
    expect(screen.queryByRole('link', { name: /TICKET/ })).toBeNull()
    expect(screen.queryByRole('link', { name: 'IG' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'MAPA' })).toBeNull()
    expect(screen.queryByRole('img')).toBeNull()
  })

  it('fechar chama onClose', async () => {
    const onClose = vi.fn()
    render(<EventDetail event={ev({})} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: /fechar|✕/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
```

E em `web/src/data/join.test.ts`, no primeiro teste, adicionar a asserção (o helper `venue()` do arquivo já tem `instagram: null` — trocar pra `instagram: "labclub"` no venue usado e conferir):
```ts
    expect(out[0].venueInstagram).toBe('labclub')
```

- [ ] **Step 2: Run tests to verify they fail**

Run (de `web/`): `npx vitest run src/components/EventDetail.test.tsx src/data/join.test.ts`
Expected: FAIL (módulo não existe / venueInstagram undefined).

- [ ] **Step 3: Write minimal implementation**

Em `data/join.ts`: `EventWithGeo` ganha `venueInstagram: string | null`; no map, adicionar `venueInstagram: v?.instagram ?? null,`.

```tsx
// web/src/components/EventDetail.tsx
import type { EventWithGeo } from '../data/join'
import { fmtDate } from './EventCard'

export function EventDetail({ event, onClose }: {
  event: EventWithGeo; onClose: () => void
}) {
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(0,0,0,.75)' }}
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ position: 'absolute', bottom: 0, left: 0, right: 0, maxWidth: 560,
                    margin: '0 auto', background: 'var(--black)', borderTop: '3px solid var(--pink)',
                    maxHeight: '92vh', overflowY: 'auto' }}>
        <button onClick={onClose} aria-label="fechar"
                style={{ position: 'absolute', top: 8, right: 8, zIndex: 2, background: 'var(--black)',
                         color: 'var(--text)', border: '2px solid var(--line)', fontWeight: 900,
                         width: 34, height: 34, cursor: 'pointer' }}>✕</button>
        {event.flyer_url && (
          <img src={event.flyer_url} alt={event.name}
               style={{ width: '100%', maxHeight: 340, objectFit: 'cover', display: 'block',
                        borderBottom: '3px solid var(--pink)' }} />
        )}
        <div style={{ padding: '12px 14px 90px' }}>
          <div className="hline" style={{ fontSize: 24 }}>{event.name}</div>
          <div style={{ color: 'var(--green)', fontWeight: 800, fontSize: 12, marginTop: 6 }}>
            {fmtDate(event.starts_at)}
          </div>
          {event.venueName && (
            <div className="meta" style={{ marginTop: 8, fontSize: 12, color: 'var(--text)', fontWeight: 700 }}>
              📍 {event.venueName}
            </div>
          )}
          <div style={{ marginTop: 10 }}>
            {event.genre && <span className="tag">{event.genre}</span>}
            <span className="tag ghost">CONF {event.effective_confidence}</span>
          </div>
        </div>
        <div style={{ position: 'sticky', bottom: 0, display: 'flex', gap: 4, padding: '10px 12px',
                      background: 'var(--black)', borderTop: '2px solid var(--line)' }}>
          {event.ticket_url && (
            <a className="b-btn primary" style={{ flex: 2 }} href={event.ticket_url}
               target="_blank" rel="noreferrer">TICKET →</a>
          )}
          {event.venueInstagram && (
            <a className="b-btn" style={{ flex: 1 }} href={`https://instagram.com/${event.venueInstagram}`}
               target="_blank" rel="noreferrer">IG</a>
          )}
          {event.mappable && event.lat != null && event.lng != null && (
            <a className="b-btn" style={{ flex: 1 }} href={`https://maps.google.com/?q=${event.lat},${event.lng}`}
               target="_blank" rel="noreferrer">MAPA</a>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (de `web/`): `npx vitest run src/components/EventDetail.test.tsx src/data/join.test.ts`
Expected: PASS. Nota: outros testes que constroem `EventWithGeo` literal (EventCard/FestasTab/venueEvents) precisam de `venueInstagram: null` no mock — adicionar onde o `tsc` apontar.

- [ ] **Step 5: Commit**

```bash
git add web/src/data/join.ts web/src/data/join.test.ts web/src/components/EventDetail.tsx web/src/components/EventDetail.test.tsx web/src/components/EventCard.test.tsx web/src/tabs/FestasTab.test.tsx web/src/data/venueEvents.test.ts web/src/data/hero.test.ts
git commit -m "feat: EventDetail (sheet com flyer grande + TICKET/IG/MAPA)

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 7: `BottomTabs` + `App` novo + rebrand do mapa + remoção do legado

**Files:**
- Create: `web/src/components/BottomTabs.tsx` (+ test)
- Modify: `web/src/App.tsx` (REESCREVER), `web/src/map/MapView.tsx` (cores/pins losango)
- Delete: `web/src/filters/FilterBar.tsx`, `web/src/filters/FilterBar.test.tsx`, `web/src/list/EventList.tsx`, `web/src/list/EventList.test.tsx`, `web/src/list/EventCard.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/components/BottomTabs.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BottomTabs } from './BottomTabs'

describe('BottomTabs', () => {
  it('marca a aba ativa e troca ao clicar', async () => {
    const onTab = vi.fn()
    render(<BottomTabs tab="festas" onTab={onTab} />)
    expect(screen.getByRole('button', { name: 'FESTAS' })).toHaveClass('on')
    await userEvent.click(screen.getByRole('button', { name: 'MAPA' }))
    expect(onTab).toHaveBeenCalledWith('mapa')
  })
})
```

- [ ] **Step 2: Run to verify it fails** — Run (de `web/`): `npx vitest run src/components/BottomTabs.test.tsx` → FAIL.

- [ ] **Step 3: Write implementation**

```tsx
// web/src/components/BottomTabs.tsx
export type Tab = 'mapa' | 'festas' | 'locais'

export function BottomTabs({ tab, onTab }: { tab: Tab; onTab: (t: Tab) => void }) {
  const tabs: { key: Tab; label: string }[] = [
    { key: 'mapa', label: 'MAPA' }, { key: 'festas', label: 'FESTAS' }, { key: 'locais', label: 'LOCAIS' },
  ]
  return (
    <div className="tabbar">
      {tabs.map((t) => (
        <button key={t.key} className={t.key === tab ? 'on' : ''} onClick={() => onTab(t.key)}>
          {t.label}
        </button>
      ))}
    </div>
  )
}
```

Reescrever `web/src/App.tsx`:

```tsx
import { useEffect, useReducer, useState } from 'react'
import './theme.css'
import { fetchEvents, fetchVenues } from './api/client'
import type { VenueOut } from './api/types'
import { joinEventsWithVenues, type EventWithGeo } from './data/join'
import { filterReducer, initialFilters, queryFromFilters } from './filters/state'
import { FestasTab } from './tabs/FestasTab'
import { MapView } from './map/MapView'
import { BottomTabs, type Tab } from './components/BottomTabs'
import { EventDetail } from './components/EventDetail'

function useIsDesktop(): boolean {
  const [is, setIs] = useState(() => window.matchMedia('(min-width: 768px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const on = (e: MediaQueryListEvent) => setIs(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return is
}

export default function App() {
  const [filters, dispatch] = useReducer(filterReducer, initialFilters)
  const [tab, setTab] = useState<Tab>('festas')
  const [events, setEvents] = useState<EventWithGeo[]>([])
  const [venues, setVenues] = useState<VenueOut[]>([])
  const [showVenues, setShowVenues] = useState(true)
  const [open, setOpen] = useState<EventWithGeo | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const isDesktop = useIsDesktop()

  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    Promise.all([fetchEvents(queryFromFilters(filters)), fetchVenues()])
      .then(([evs, vns]) => { if (alive) { setEvents(joinEventsWithVenues(evs, vns)); setVenues(vns) } })
      .catch((e) => { if (alive) setError(String(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [filters, reloadKey])

  const openEvent = (e: EventWithGeo) => { setOpen(e); setSelectedId(e.id) }

  const mapa = (
    <MapView events={events} venues={venues} selectedId={selectedId}
             onSelect={(id) => { const e = events.find((x) => x.id === id); if (e) openEvent(e) }}
             showVenues={showVenues} />
  )
  const festas = <FestasTab events={events} filters={filters} dispatch={dispatch} onOpen={openEvent} />
  const locais = <div className="empty" style={{ paddingTop: 80 }}>LOCAIS — em breve (Plano C-2)</div>

  if (error) {
    return (
      <div className="empty" style={{ paddingTop: 80 }}>
        Não consegui falar com a API — o uvicorn está no ar? ({error})
        <div style={{ marginTop: 12 }}>
          <button className="chip" onClick={() => setReloadKey((k) => k + 1)}>TENTAR DE NOVO</button>
        </div>
      </div>
    )
  }
  if (loading) return <div className="empty" style={{ paddingTop: 80 }}>CARREGANDO…</div>

  if (isDesktop) {
    return (
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
        <div className="d-header">
          <span>RADAR★SP</span>
          <nav>
            <span className={tab !== 'locais' ? 'on' : ''} onClick={() => setTab('festas')}>FESTAS</span>
            <span className={tab === 'locais' ? 'on' : ''} onClick={() => setTab('locais')}>LOCAIS</span>
          </nav>
          <span style={{ fontSize: 11 }}>{events.length} FESTAS</span>
        </div>
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div style={{ width: '40%', overflowY: 'auto', borderRight: '3px solid var(--pink)' }}>
            {tab === 'locais' ? locais : festas}
          </div>
          <div style={{ flex: 1 }}>{mapa}</div>
        </div>
        {open && <EventDetail event={open} onClose={() => setOpen(null)} />}
      </div>
    )
  }

  return (
    <div style={{ height: '100vh' }}>
      {tab === 'mapa' && <div style={{ position: 'fixed', inset: 0, bottom: 44 }}>{mapa}</div>}
      {tab === 'festas' && <div style={{ height: '100%', overflowY: 'auto' }}>{festas}</div>}
      {tab === 'locais' && locais}
      <BottomTabs tab={tab} onTab={setTab} />
      {open && <EventDetail event={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
```

Rebrand do `map/MapView.tsx` (só estilo — lógica intacta):
1. Marker de evento: o `<div>` circular vira **losango brutalista**:
```tsx
          <div style={{
            width: 13, height: 13,
            background: e.id === selectedId ? 'var(--green)' : 'var(--pink)',
            transform: 'rotate(45deg)', border: '2px solid #000',
            cursor: 'pointer',
          }} />
```
2. Camada de venues: `circle-color` de `#5a6b8a` → `'#00ff85'` com `'circle-opacity': 0.45`; `venue-sel` → `'circle-color': '#00ff85'`, opacity 1.

Deletar os arquivos legados: `git rm web/src/filters/FilterBar.tsx web/src/filters/FilterBar.test.tsx web/src/list/EventList.tsx web/src/list/EventList.test.tsx web/src/list/EventCard.tsx`.

- [ ] **Step 4: Verificação completa**

Run (de `web/`): `npx tsc -b --noEmit` (corrigir mocks faltando `flyer_url`/`venueInstagram` que apontar) e depois `npx vitest run`.
Expected: tsc limpo; suíte web toda verde (os testes antigos de FilterBar/EventList saíram junto com os componentes — substituídos por FilterChips/FestasTab/EventCard/BottomTabs/EventDetail).

- [ ] **Step 5: Commit**

```bash
git add -A web/src web/index.html
git commit -m "feat: App brutalista (3 abas, breakpoint 768, detail) + rebrand do mapa; remove FilterBar/EventList legados

Claude-Session: https://claude.ai/code/session_01CxEvzDvGEmEHYT6fNXD4cu"
```

---

### Task 8: suítes + smoke visual + merge (CONTROLADOR)

- [ ] **Step 1:** Suítes completas: pytest (`--basetemp`) + `npx vitest run` + `npx tsc -b --noEmit` — tudo verde por exit code.
- [ ] **Step 2:** Subir uvicorn `:8001` + vite; abrir no navegador: feed FESTAS com flyers REAIS (o banco tem 12+ de @blitzhaus/@homeclubsp), hero destacado, chips trocando preset, detalhe abrindo com TICKET/IG/MAPA, abas navegando, desktop 40/60, mapa com pins losango. Validação pelo usuário.
- [ ] **Step 3:** Code-review adversarial do diff da branch; aplicar fixes procedentes.
- [ ] **Step 4:** Merge `--no-ff` no master; suítes no master; memória.

---

## Notas de implementação

- **Ordem de dependência:** T2 (tema/tipos) → T3-T6 (componentes, cada um testável isolado) → T7 (App religa tudo e remove o legado). A UI só "muda de cara" de fato no T7 — merges intermediários não acontecem (é uma branch só).
- **Mocks de `EventWithGeo`/`EventOut`:** os campos novos (`flyer_url`, `venueInstagram`) quebram mocks literais existentes via tsc — cada task corrige os que tocar; o T7 roda o tsc geral.
- **`fmtDate` exportado do EventCard novo** — o EventDetail reusa (DRY).
- **MapView:** sem teste unitário (canvas) — padrão do projeto; o smoke do T8 valida os pins novos.
