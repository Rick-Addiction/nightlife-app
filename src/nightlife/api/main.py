# src/nightlife/api/main.py
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from .. import config
from ..domain.freshness import freshness_factor
from ..domain.nightlife_relevance import is_buffet_name, venue_relevance
from ..models import AreaSweep, Event, EventSource, Venue, VenueSource
from .deps import get_session
from .schemas import AreaSweepIn, AreaSweepOut, EventOut, VenueOut

app = FastAPI(title="Nightlife SP — API")

_IG_PERMALINK = re.compile(r"instagram\.com/p/([A-Za-z0-9_-]+)")
# so serve imagem com nome no formato shortcode.ext — sidecars .json e
# qualquer path fora do padrao respondem 404 (M1); dir lido em request-time (M3)
_FLYER_FILE = re.compile(r"^[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)$")
# "dia" de evento = dia do CALENDARIO em Sao Paulo (disciplina do projeto).
# Comparar timestamptz com a DATE crua vira meia-noite UTC: HOJE/AMANHA
# (date_from == date_to) davam janela de largura ZERO, e sabado 23h SP
# (= domingo 02h UTC) escapava ate do fim de semana.
_SP_TZ = ZoneInfo("America/Sao_Paulo")


def _sp_day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=_SP_TZ)


@app.api_route("/flyers/{filename}", methods=["GET", "HEAD"])
def get_flyer(filename: str):
    if not _FLYER_FILE.fullmatch(filename):
        raise HTTPException(status_code=404, detail="flyer nao encontrado")
    path = config.FLYERS_PROCESSED_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="flyer nao encontrado")
    return FileResponse(path)


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
        .order_by(EventSource.id)   # deterministico: 1a evidencia vence
    ).all()
    for eid, url in rows:
        m = _IG_PERMALINK.search(url or "")
        if m and m.group(1) in files and eid not in out:
            out[eid] = f"/flyers/{files[m.group(1)]}"
    return out


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox deve ser 'minLng,minLat,maxLng,maxLat'") from exc
    return min_lng, min_lat, max_lng, max_lat


def _with_effective(out_cls, entity, now: datetime):
    out = out_cls.model_validate(entity)
    out.effective_confidence = round(entity.confidence * freshness_factor(entity.last_seen_at, now))
    return out


@app.get("/venues", response_model=list[VenueOut])
def list_venues(
    type: str | None = None,
    bbox: str | None = None,
    min_confidence: int = 0,
    include_all: bool = False,
    session: Session = Depends(get_session),
):
    # pre-filtro no SQL pelo score armazenado e valido: effective <= stored
    q = select(Venue).where(Venue.confidence >= min_confidence)
    if type is not None:
        q = q.where(Venue.category == type)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    venues = session.scalars(q).all()
    gp_ids = set(session.scalars(
        select(distinct(VenueSource.venue_id))
        .where(VenueSource.source_type == "google_places")
    ).all())
    if not include_all:
        with_events = set(session.scalars(
            select(Event.venue_id).where(Event.venue_id.is_not(None))
        ).all())
        source_counts = dict(session.execute(
            select(VenueSource.venue_id, func.count(distinct(VenueSource.source_type)))
            .group_by(VenueSource.venue_id)
        ).all())
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        venues = [
            v for v in venues
            if venue_relevance(
                v.name, v.category, v.id in with_events, v.is_monitored,
                places_verified=v.id in gp_ids,
                business_status=v.business_status,
                source_count=source_counts.get(v.id, 0),
                has_contact=bool(v.instagram or v.website),
                ig_stale=(v.ig_last_post_at is not None and v.ig_last_post_at < stale_cutoff),
            ) == "relevant"
        ]
    now = datetime.now(timezone.utc)
    outs = [_with_effective(VenueOut, v, now) for v in venues]
    for o in outs:
        o.places_verified = o.id in gp_ids
    outs = [o for o in outs if o.effective_confidence >= min_confidence]
    outs.sort(key=lambda o: o.effective_confidence, reverse=True)
    return outs


@app.get("/venues/{venue_id}", response_model=VenueOut)
def get_venue(venue_id: int, session: Session = Depends(get_session)):
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue nao encontrado")
    out = _with_effective(VenueOut, venue, datetime.now(timezone.utc))
    out.places_verified = bool(session.scalar(
        select(func.count()).select_from(VenueSource)
        .where(VenueSource.venue_id == venue_id,
               VenueSource.source_type == "google_places")
    ))
    return out


@app.get("/events", response_model=list[EventOut])
def list_events(
    date_from: date | None = None,
    date_to: date | None = None,
    bbox: str | None = None,
    genre: str | None = None,
    min_confidence: int = 0,
    include_past: bool = False,
    include_all: bool = False,
    session: Session = Depends(get_session),
):
    if date_from is None and not include_past:
        # default: so eventos futuros — a lista nao acumula passado eternamente
        date_from = date.today()
    q = select(Event).where(Event.confidence >= min_confidence)
    if date_from is not None:
        q = q.where(Event.starts_at >= _sp_day_start(date_from))
    if date_to is not None:
        # limite superior EXCLUSIVO no inicio do dia seguinte (SP): inclui a
        # madrugada inteira do proprio date_to
        q = q.where(Event.starts_at < _sp_day_start(date_to + timedelta(days=1)))
    if genre is not None:
        q = q.where(Event.genre == genre)
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
        q = q.join(Venue, Event.venue_id == Venue.id).where(
            Venue.lat >= min_lat, Venue.lat <= max_lat,
            Venue.lng >= min_lng, Venue.lng <= max_lng,
        )
    now = datetime.now(timezone.utc)
    outs = [_with_effective(EventOut, e, now)
            for e in session.scalars(q.order_by(Event.starts_at)).all()]
    outs = [o for o in outs if o.effective_confidence >= min_confidence]
    if not include_all:
        # projeta (id, name) em vez de hidratar Venue inteiro por request
        blocked_ids = {
            vid for vid, vname in session.execute(select(Venue.id, Venue.name)).all()
            if is_buffet_name(vname)
        }
        outs = [o for o in outs if o.venue_id not in blocked_ids]
    flyers = _flyer_urls_for(session, [o.id for o in outs])
    for o in outs:
        o.flyer_url = flyers.get(o.id)
    return outs


@app.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="evento nao encontrado")
    out = _with_effective(EventOut, event, datetime.now(timezone.utc))
    out.flyer_url = _flyer_urls_for(session, [event.id]).get(event.id)
    return out


def _spawn_sweep(sweep_id: int) -> int:
    """Subprocesso DESTACADO (sobrevive a API): o runner faz o trabalho."""
    cmd = [sys.executable, "-m", "nightlife.sweep_area", "--sweep-id", str(sweep_id),
           "--center", "0,0"]  # center ignorado quando --sweep-id existe
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    Path("logs").mkdir(exist_ok=True)
    log = open(f"logs/sweep_{sweep_id}.log", "ab")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=flags, close_fds=True)
    return proc.pid


@app.post("/admin/area-sweeps", status_code=202)
def start_area_sweep(body: AreaSweepIn, session: Session = Depends(get_session)):
    running = session.scalars(select(AreaSweep).where(AreaSweep.status == "running")).first()
    if running is not None:
        raise HTTPException(status_code=409,
                            detail=f"varredura #{running.id} ja esta rodando")
    sweep = AreaSweep(center_lat=body.lat, center_lng=body.lng, radius_km=body.km,
                      started_at=datetime.now(timezone.utc))
    session.add(sweep)
    session.flush()
    sweep.pid = _spawn_sweep(sweep.id)
    session.commit()
    return {"id": sweep.id}


@app.get("/admin/area-sweeps/current", response_model=AreaSweepOut)
def get_current_sweep(session: Session = Depends(get_session)):
    sweep = session.scalars(select(AreaSweep).order_by(AreaSweep.id.desc())).first()
    if sweep is None:
        raise HTTPException(status_code=404, detail="nenhuma varredura ainda")
    out = AreaSweepOut.model_validate(sweep)
    out.done_handles = len(sweep.report or [])
    return out
