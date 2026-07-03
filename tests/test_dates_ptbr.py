# tests/test_dates_ptbr.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from nightlife.domain.dates_ptbr import parse_ptbr_datetime

SP = ZoneInfo("America/Sao_Paulo")
REF = date(2026, 6, 1)  # segunda-feira


def test_dd_mm_yyyy_is_exact():
    r = parse_ptbr_datetime("13/06/2026", reference=REF)
    assert r.dt == datetime(2026, 6, 13, 0, 0, tzinfo=SP)
    assert r.ambiguous is False


def test_dd_mm_without_year_infers_and_flags_ambiguous():
    r = parse_ptbr_datetime("festa dia 13/06", reference=REF)
    assert r.dt == datetime(2026, 6, 13, 0, 0, tzinfo=SP)
    assert r.ambiguous is True


def test_dd_mm_already_past_rolls_to_next_year():
    r = parse_ptbr_datetime("05/01", reference=REF)  # 5 jan < 1 jun -> proximo ano
    assert r.dt == datetime(2027, 1, 5, 0, 0, tzinfo=SP)
    assert r.ambiguous is True


def test_month_name_with_optional_de():
    r = parse_ptbr_datetime("13 de junho", reference=REF)
    assert r.dt.month == 6 and r.dt.day == 13
    r2 = parse_ptbr_datetime("SAB 13 JUN", reference=REF)
    assert r2.dt.month == 6 and r2.dt.day == 13


def test_weekday_next_occurrence():
    r = parse_ptbr_datetime("rola na sexta", reference=REF)  # ref=segunda -> sexta = +4
    assert r.dt == datetime(2026, 6, 5, 0, 0, tzinfo=SP)


def test_hoje_amanha():
    assert parse_ptbr_datetime("hoje", reference=REF).dt.day == 1
    assert parse_ptbr_datetime("amanha", reference=REF).dt.day == 2


def test_time_is_extracted():
    r = parse_ptbr_datetime("13/06 23h30", reference=REF)
    assert (r.dt.hour, r.dt.minute) == (23, 30)
    r2 = parse_ptbr_datetime("13/06 as 22h", reference=REF)
    assert (r2.dt.hour, r2.dt.minute) == (22, 0)


def test_no_date_returns_none():
    r = parse_ptbr_datetime("line-up insano sem data", reference=REF)
    assert r.dt is None
    assert r.matched is None


def test_invalid_date_returns_none():
    r = parse_ptbr_datetime("40/13/2026", reference=REF)
    assert r.dt is None


def test_price_label_is_not_a_time():
    # "Lote 2:" / "Area 2:" nao sao horarios; o horario real vem depois
    r = parse_ptbr_datetime("GOP TUN\nLote 2: R$ 30\nsabado 22h", reference=REF)
    assert (r.dt.hour, r.dt.minute) == (22, 0)
    r2 = parse_ptbr_datetime("Area 2: som a partir das 22h, dia 20/07", reference=REF)
    assert r2.dt.hour == 22 and r2.dt.day == 20


def test_invalid_slash_token_falls_through_to_real_date():
    # preco "20/40" e "24/7" nao podem engolir a data real que vem depois
    r = parse_ptbr_datetime("Ingressos R$ 20/40 - 13 de junho no Club X", reference=REF)
    assert r.dt is not None and (r.dt.day, r.dt.month) == (13, 6)
    r2 = parse_ptbr_datetime("open bar 24/7 sabado 22h", reference=REF)
    assert r2.dt is not None and r2.dt.weekday() == 5  # sabado, nao 24/jul


def test_feb29_rollover_does_not_crash():
    # 29/02 com rollover para ano nao-bissexto: retorna None, nao explode
    r = parse_ptbr_datetime("29/02 22h", reference=date(2028, 6, 1))
    assert r.dt is None
    r2 = parse_ptbr_datetime("29 de fevereiro", reference=date(2028, 6, 1))
    assert r2.dt is None


def test_weekday_word_collision():
    # "ter" (verbo) nao pode sequestrar o dia; o nome completo vence
    r = parse_ptbr_datetime("Sabado vai ter GOP TUN, 16h", reference=REF)
    assert r.dt.weekday() == 5 and r.dt.hour == 16
    # sem dia nenhum, "vai ter" nao inventa uma terca
    assert parse_ptbr_datetime("vai ter open bar", reference=REF).dt is None
    # abreviacao MAIUSCULA continua valendo
    assert parse_ptbr_datetime("SEX · Club X · 23h", reference=REF).dt.weekday() == 4
