"""Czysta logika 'godzin ciszy' - pomiń cykl odczytu (i wywołanie AI) w
skonfigurowanym oknie czasowym, żeby nie zużywać tokenów/zapytań w porach,
gdy zmiana odczytu jest mało prawdopodobna (np. noc). Bez zależności od
HA/sieci."""
from __future__ import annotations

from datetime import time


def parse_hhmm(value: str | None) -> time | None:
    """Parsuje 'GG:MM' na datetime.time. Pusty/brakujący string -> None
    (funkcja wyłączona)."""
    if not value:
        return None
    hours, minutes = value.split(":")[:2]
    return time(int(hours), int(minutes))


def is_within_quiet_hours(now: time, start: time | None, end: time | None) -> bool:
    """Czy `now` mieści się w oknie [start, end).

    Obsługuje okno przechodzące przez północ (np. 23:00 -> 06:00, gdzie
    start > end) tak samo jak zwykłe okno w obrębie jednego dnia. Brak
    jednej z granic albo start == end (okno zerowej długości - niejasna
    intencja) traktujemy jako wyłączone, nie jako "cały dzień"."""
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end
