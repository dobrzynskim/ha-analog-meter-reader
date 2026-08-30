"""Czysta logika parsowania/walidacji odczytu AI - bez zależności od HA/sieci.

Konsoliduje w jednym, testowalnym miejscu logikę, która wcześniej żyła
podwójnie: raz w skrypcie cron (odrzucenie lokalne + korekta przesuniętego
przecinka) i raz w szablonie Jinja po stronie Home Assistant (ten sam
warunek "licznik się nie cofa i nie skacze za bardzo", przepisany od nowa
w YAML).
"""
from __future__ import annotations

import re

from .const import UNCERTAIN_MARKER

VALUE_RE = re.compile(r"^\d{1,6}\.\d{1,3}$")

# Współczynniki przesunięcia przecinka, które AI myli najczęściej (np. zwraca
# 5.153 zamiast 515.3) - to błąd w liczbie cyfr "przed kropką", nie losowy szum.
_SHIFT_FACTORS = (10, 100, 1000)


def parse_ai_response(text: str) -> float | None:
    """Zwraca odczyt jako float, albo None jeśli AI nie było pewne / zła odpowiedź."""
    text = text.strip()
    if text == UNCERTAIN_MARKER or not VALUE_RE.match(text):
        return None
    return float(text)


def try_fix_decimal_shift(value: float, last_good: float, max_step: float) -> float | None:
    """Próbuje skorygować przesunięty przecinek (patrz docstring modułu).

    Jeśli przeskalowanie o 10/100/1000 w górę lub w dół daje wartość, której
    część całkowita pasuje do ostatniego dobrego odczytu (z zachowaniem
    max_step), uznajemy to za poprawną korektę zamiast odrzucać cały odczyt.
    """
    for factor in _SHIFT_FACTORS:
        for candidate in (value * factor, value / factor):
            if int(candidate) >= int(last_good) and int(candidate) - int(last_good) <= max_step:
                return round(candidate, 3)
    return None


def validate_reading(
    value: float, last_good: float | None, max_step: float
) -> tuple[float, bool]:
    """Zwraca (wartość_do_użycia, czy_surowy_odczyt_odrzucony).

    Licznik nigdy się nie cofa, a w jednym cyklu nie przybywa nierealistycznie
    dużo - jeśli tak wygląda surowy odczyt, spróbuj skorygować przesunięty
    przecinek; jeśli się nie da, zostań przy ostatniej dobrej wartości
    (surowy odczyt i tak trafia do atrybutów encji, żeby było widać co AI
    faktycznie zwróciło).
    """
    if last_good is None:
        return value, False
    if value < last_good or (value - last_good) > max_step:
        fixed = try_fix_decimal_shift(value, last_good, max_step)
        if fixed is not None:
            return fixed, False
        return last_good, True
    return value, False
