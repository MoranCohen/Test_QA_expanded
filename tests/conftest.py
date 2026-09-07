"""
Shared pytest fixtures for the ammeter test suite.
"""
import pytest

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter

# ---------------------------------------------------------------------------
# Port constants – mirrors the values in main.py
# ---------------------------------------------------------------------------

GREENLEE_PORT: int = 5001
ENTES_PORT: int = 5002
CIRCUTOR_PORT: int = 5003

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def greenlee_ammeter() -> GreenleeAmmeter:
    """Return a fresh GreenleeAmmeter instance bound to GREENLEE_PORT."""
    return GreenleeAmmeter(GREENLEE_PORT)


@pytest.fixture(scope="function")
def entes_ammeter() -> EntesAmmeter:
    """Return a fresh EntesAmmeter instance bound to ENTES_PORT."""
    return EntesAmmeter(ENTES_PORT)


@pytest.fixture(scope="function")
def circutor_ammeter() -> CircutorAmmeter:
    """Return a fresh CircutorAmmeter instance bound to CIRCUTOR_PORT."""
    return CircutorAmmeter(CIRCUTOR_PORT)