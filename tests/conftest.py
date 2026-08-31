"""Udostępnia analog_meter_reader.{validation,image,api,const} do importu bez
wymagania homeassistant.

validation.py używa importu względnego (`from .const import ...`), więc musi
być importowany jako submoduł pakietu - ale prawdziwy
custom_components/analog_meter_reader/__init__.py importuje homeassistant, co
nie powinno być potrzebne do testowania czystej logiki. Podstawiamy pusty
pakiet-atrapę wskazujący na ten sam katalog, żeby import względny się
rozwiązał bez uruchamiania prawdziwego __init__.py."""

import sys
import types
from pathlib import Path

import pytest

_COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "analog_meter_reader"

_pkg = types.ModuleType("analog_meter_reader")
_pkg.__path__ = [str(_COMPONENT_DIR)]
sys.modules.setdefault("analog_meter_reader", _pkg)

# api.py/image.py mają zero importów względnych - importowalne wprost, jeśli
# katalog integracji jest na sys.path (bez tego tylko `validation.py`, przez
# swój `from .const import ...`, byłoby dostępne - jako submodule pakietu-atrapy powyżej).
sys.path.insert(0, str(_COMPONENT_DIR))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """test_coordinator.py/test_config_flow.py importują i uruchamiają
    prawdziwy custom_components/analog_meter_reader (przez `hass`) - HA domyślnie
    ignoruje custom_components podczas testów, ta fixture (z
    pytest-homeassistant-custom-component) to odblokowuje."""
    yield
