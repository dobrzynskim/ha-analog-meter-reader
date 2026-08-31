"""Buduje domyślny prompt AI z konfigurowalnych kolorów cyfr licznika.

Wydzielone z coordinator.py, żeby dało się to przetestować bez homeassistant
(ta sama zasada co validation.py/schedule.py) - i żeby _async_update_data nie
puchło o budowanie stringów."""
from __future__ import annotations

from .const import DEFAULT_PROMPT_TEMPLATE, UNCERTAIN_MARKER


def build_default_prompt(whole_color: str, fraction_color: str) -> str:
    """Prompt dopasowany do kolorów cyfr TEGO konkretnego licznika.

    Nie każdy licznik ma czarne cyfry pełnych jednostek i czerwone cyfry
    ułamka (patrz const.DEFAULT_WHOLE_DIGIT_COLOR/DEFAULT_FRACTION_DIGIT_COLOR)
    - to tylko najpopularniejszy układ w licznikach wody/gazu."""
    return DEFAULT_PROMPT_TEMPLATE.format(
        whole_color=whole_color.capitalize(),
        whole_color_upper=whole_color.upper(),
        fraction_color=fraction_color,
        uncertain_marker=UNCERTAIN_MARKER,
    )
