"""
Unit tests for CircutorAmmeter, EntesAmmeter, and GreenleeAmmeter.

Test naming convention: test_<what>_<condition>_<expected_result>
Test classes:          Test<SystemUnderTest>

All network I/O is mocked via unittest.mock.patch so these tests run
without a live server.  Tests that require a live server are tagged
@pytest.mark.integration and are excluded from the default run.

Rule 8 compliance: tests that differ only in ammeter type / port / command
use @pytest.mark.parametrize. Dedicated test classes contain only the
ammeter-specific tests (exact error messages, exact byte commands) that
cannot be expressed generically without losing specificity.
"""
import pytest
from unittest.mock import patch, MagicMock

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.client import request_current_from_ammeter

# ---------------------------------------------------------------------------
# Named constants — Rule 5: no magic values
# ---------------------------------------------------------------------------

CIRCUTOR_EXPECTED_COMMAND: bytes = b'MEASURE_CIRCUTOR -get_measurement -current'
ENTES_EXPECTED_COMMAND: bytes = b'MEASURE_ENTES -get_data'
GREENLEE_EXPECTED_COMMAND: bytes = b'MEASURE_GREENLEE -get_measurement'

GREENLEE_PORT: int = 5001
ENTES_PORT: int = 5002
CIRCUTOR_PORT: int = 5003

# Greenlee: voltage 1–10 V, resistance 0.1–100 Ω → current in (0.01, 100) A
GREENLEE_CURRENT_MIN: float = 0.01
GREENLEE_CURRENT_MAX: float = 100.0

# Entes: magnetic_field 0.01–0.1 T × calibration 500–2000 → current in (5, 200) A
ENTES_CURRENT_MIN: float = 5.0
ENTES_CURRENT_MAX: float = 200.0

# Circutor: 10 voltages 0.1–1.0 V × time_step 0.001–0.01 s → current in (0.001, 0.1) A
CIRCUTOR_CURRENT_MIN: float = 0.001
CIRCUTOR_CURRENT_MAX: float = 0.1

INVALID_COMMAND: bytes = b'INVALID_COMMAND'
MOCK_CURRENT_VALUE: float = 4.75
NUM_MEASURE_SAMPLES: int = 100
FLOAT_TOLERANCE: float = 1e-9

CIRCUTOR_ERROR_MSG: str = "ADC failure"
ENTES_ERROR_MSG: str = "sensor fault"
GREENLEE_ERROR_MSG: str = "bus fault"

# Pinned boundary values for deterministic boundary tests (Rule 13)
# Circutor: time_step first, then 10 voltages; current = sum(v * t for v in voltages)
CIRCUTOR_BOUNDARY_TIME_STEP_MIN: float = 0.001
CIRCUTOR_BOUNDARY_VOLTAGE_MIN: float = 0.1
CIRCUTOR_BOUNDARY_EXPECTED_MIN: float = 0.001   # 10 * 0.1 * 0.001
CIRCUTOR_BOUNDARY_TIME_STEP_MAX: float = 0.01
CIRCUTOR_BOUNDARY_VOLTAGE_MAX: float = 1.0
CIRCUTOR_BOUNDARY_EXPECTED_MAX: float = 0.1     # 10 * 1.0 * 0.01
CIRCUTOR_NUM_VOLTAGES: int = 10

# Entes: magnetic_field * calibration_factor
ENTES_BOUNDARY_FIELD_MIN: float = 0.01
ENTES_BOUNDARY_CALIBRATION_MIN: float = 500.0
ENTES_BOUNDARY_EXPECTED_MIN: float = 5.0        # 0.01 * 500
ENTES_BOUNDARY_FIELD_MAX: float = 0.1
ENTES_BOUNDARY_CALIBRATION_MAX: float = 2000.0
ENTES_BOUNDARY_EXPECTED_MAX: float = 200.0      # 0.1 * 2000

# Greenlee: voltage / resistance
GREENLEE_BOUNDARY_VOLTAGE_MIN: float = 1.0
GREENLEE_BOUNDARY_RESISTANCE_MAX: float = 100.0
GREENLEE_BOUNDARY_EXPECTED_MIN: float = 0.01    # 1.0 / 100.0
GREENLEE_BOUNDARY_VOLTAGE_MAX: float = 10.0
GREENLEE_BOUNDARY_RESISTANCE_MIN: float = 0.1
GREENLEE_BOUNDARY_EXPECTED_MAX: float = 100.0   # 10.0 / 0.1

# ---------------------------------------------------------------------------
# Parametrize table — Rule 8: single source of truth for repeated shapes
# ---------------------------------------------------------------------------

_AMMETER_PARAMS = [
    (CircutorAmmeter, CIRCUTOR_PORT, CIRCUTOR_EXPECTED_COMMAND,
     CIRCUTOR_CURRENT_MIN, CIRCUTOR_CURRENT_MAX),
    (EntesAmmeter,    ENTES_PORT,    ENTES_EXPECTED_COMMAND,
     ENTES_CURRENT_MIN,    ENTES_CURRENT_MAX),
    (GreenleeAmmeter, GREENLEE_PORT, GREENLEE_EXPECTED_COMMAND,
     GREENLEE_CURRENT_MIN, GREENLEE_CURRENT_MAX),
]
_AMMETER_IDS = ["circutor", "entes", "greenlee"]

# ---------------------------------------------------------------------------
# TestCircutorAmmeter — dedicated class (Rule 14)
# Contains only tests unique to Circutor (exact command byte string and
# error-condition test with the Circutor-specific error message).
# Generic happy-path / range / type tests are in the parametrized section.
# ---------------------------------------------------------------------------


class TestCircutorAmmeter:
    """Dedicated test class for CircutorAmmeter (Rule 14).

    Contains tests specific to Circutor: exact command byte string, error message,
    and invalid-input handling.
    """

    def test_get_current_command_returns_exact_byte_string(
        self, circutor_ammeter: CircutorAmmeter
    ) -> None:
        # Arrange — fixture provides a CircutorAmmeter instance
        # Act
        result = circutor_ammeter.get_current_command
        # Assert
        assert result == CIRCUTOR_EXPECTED_COMMAND, (
            f"CircutorAmmeter.get_current_command must equal {CIRCUTOR_EXPECTED_COMMAND!r}; "
            f"got {result!r}"
        )

    def test_measure_current_invalid_input_raises_when_utility_returns_non_numeric(
        self, circutor_ammeter: CircutorAmmeter
    ) -> None:
        # Arrange — patch generate_random_float to return a non-numeric value
        with patch(
            "Ammeters.Circutor_Ammeter.generate_random_float",
            return_value="bad",
        ):
            # Assert
            with pytest.raises(TypeError, match="can't multiply sequence"):
                # Act
                circutor_ammeter.measure_current()

    def test_measure_current_error_condition_raises_when_utility_fails(
        self, circutor_ammeter: CircutorAmmeter
    ) -> None:
        # Arrange — patch generate_random_float to simulate a utility failure
        with patch(
            "Ammeters.Circutor_Ammeter.generate_random_float",
            side_effect=RuntimeError(CIRCUTOR_ERROR_MSG),
        ):
            # Assert
            with pytest.raises(RuntimeError, match=CIRCUTOR_ERROR_MSG):
                # Act
                circutor_ammeter.measure_current()


# ---------------------------------------------------------------------------
# TestEntesAmmeter — dedicated class (Rule 14)
# ---------------------------------------------------------------------------


class TestEntesAmmeter:
    """Dedicated test class for EntesAmmeter (Rule 14).

    Contains tests specific to Entes: exact command byte string, error message,
    and invalid-input handling.
    """

    def test_get_current_command_returns_exact_byte_string(
        self, entes_ammeter: EntesAmmeter
    ) -> None:
        # Arrange — fixture provides an EntesAmmeter instance
        # Act
        result = entes_ammeter.get_current_command
        # Assert
        assert result == ENTES_EXPECTED_COMMAND, (
            f"EntesAmmeter.get_current_command must equal {ENTES_EXPECTED_COMMAND!r}; "
            f"got {result!r}"
        )

    def test_measure_current_invalid_input_raises_when_utility_returns_non_numeric(
        self, entes_ammeter: EntesAmmeter
    ) -> None:
        # Arrange — patch generate_random_float to return a non-numeric value
        with patch(
            "Ammeters.Entes_Ammeter.generate_random_float",
            return_value="bad",
        ):
            # Assert
            with pytest.raises(TypeError, match="can't multiply sequence"):
                # Act
                entes_ammeter.measure_current()

    def test_measure_current_error_condition_raises_when_utility_fails(
        self, entes_ammeter: EntesAmmeter
    ) -> None:
        # Arrange — patch generate_random_float to simulate a utility failure
        with patch(
            "Ammeters.Entes_Ammeter.generate_random_float",
            side_effect=RuntimeError(ENTES_ERROR_MSG),
        ):
            # Assert
            with pytest.raises(RuntimeError, match=ENTES_ERROR_MSG):
                # Act
                entes_ammeter.measure_current()


# ---------------------------------------------------------------------------
# TestGreenleeAmmeter — dedicated class (Rule 14)
# ---------------------------------------------------------------------------


class TestGreenleeAmmeter:
    """Dedicated test class for GreenleeAmmeter (Rule 14).

    Contains tests specific to Greenlee: exact command byte string, error message,
    and invalid-input handling.
    """

    def test_get_current_command_returns_exact_byte_string(
        self, greenlee_ammeter: GreenleeAmmeter
    ) -> None:
        # Arrange — fixture provides a GreenleeAmmeter instance
        # Act
        result = greenlee_ammeter.get_current_command
        # Assert
        assert result == GREENLEE_EXPECTED_COMMAND, (
            f"GreenleeAmmeter.get_current_command must equal {GREENLEE_EXPECTED_COMMAND!r}; "
            f"got {result!r}"
        )

    def test_measure_current_invalid_input_raises_when_utility_returns_non_numeric(
        self, greenlee_ammeter: GreenleeAmmeter
    ) -> None:
        # Arrange — patch generate_random_float to return a non-numeric value
        with patch(
            "Ammeters.Greenlee_Ammeter.generate_random_float",
            return_value="bad",
        ):
            # Assert
            with pytest.raises(TypeError, match="unsupported operand type"):
                # Act
                greenlee_ammeter.measure_current()

    def test_measure_current_error_condition_raises_when_utility_fails(
        self, greenlee_ammeter: GreenleeAmmeter
    ) -> None:
        # Arrange — patch generate_random_float to simulate a utility failure
        with patch(
            "Ammeters.Greenlee_Ammeter.generate_random_float",
            side_effect=RuntimeError(GREENLEE_ERROR_MSG),
        ):
            # Assert
            with pytest.raises(RuntimeError, match=GREENLEE_ERROR_MSG):
                # Act
                greenlee_ammeter.measure_current()


# ---------------------------------------------------------------------------
# Parametrized tests — Rule 8: collapse tests differing only in ammeter type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ammeter_class, port, expected_command, current_min, current_max",
    _AMMETER_PARAMS,
    ids=_AMMETER_IDS,
)
def test_get_current_command_all_ammeters_return_exact_byte_string(
    ammeter_class: type,
    port: int,
    expected_command: bytes,
    current_min: float,
    current_max: float,
) -> None:
    # Arrange
    ammeter = ammeter_class(port)
    # Act
    result = ammeter.get_current_command
    # Assert
    assert result == expected_command, (
        f"{ammeter_class.__name__}.get_current_command must equal {expected_command!r}; "
        f"got {result!r}"
    )


@pytest.mark.parametrize(
    "ammeter_class, port, expected_command, current_min, current_max",
    _AMMETER_PARAMS,
    ids=_AMMETER_IDS,
)
def test_get_current_command_all_ammeters_return_bytes_type(
    ammeter_class: type,
    port: int,
    expected_command: bytes,
    current_min: float,
    current_max: float,
) -> None:
    # Arrange
    ammeter = ammeter_class(port)
    # Act
    result = ammeter.get_current_command
    # Assert
    assert isinstance(result, bytes), (
        f"{ammeter_class.__name__}.get_current_command must return bytes, "
        f"got {type(result).__name__}"
    )


@pytest.mark.parametrize(
    "ammeter_class, port, expected_command, current_min, current_max",
    _AMMETER_PARAMS,
    ids=_AMMETER_IDS,
)
def test_measure_current_all_ammeters_happy_path_returns_float(
    ammeter_class: type,
    port: int,
    expected_command: bytes,
    current_min: float,
    current_max: float,
) -> None:
    # Arrange
    ammeter = ammeter_class(port)
    # Act
    result = ammeter.measure_current()
    # Assert — type only (Rule 3: one logical assertion per test)
    assert isinstance(result, float), (
        f"{ammeter_class.__name__}.measure_current() must return float, "
        f"got {type(result).__name__}"
    )


@pytest.mark.parametrize(
    "ammeter_class, port, expected_command, current_min, current_max",
    _AMMETER_PARAMS,
    ids=_AMMETER_IDS,
)
def test_measure_current_all_ammeters_happy_path_within_plausible_range(
    ammeter_class: type,
    port: int,
    expected_command: bytes,
    current_min: float,
    current_max: float,
) -> None:
    # Arrange
    ammeter = ammeter_class(port)
    # Act
    result = ammeter.measure_current()
    # Assert — range only (Rule 3: separate from type check above)
    assert current_min <= result <= current_max, (
        f"{ammeter_class.__name__}.measure_current() returned {result}, "
        f"expected value in [{current_min}, {current_max}] A"
    )


@pytest.mark.parametrize(
    "ammeter_class, port, expected_command, current_min, current_max",
    _AMMETER_PARAMS,
    ids=_AMMETER_IDS,
)
def test_measure_current_all_ammeters_boundary_repeated_calls_all_in_range(
    ammeter_class: type,
    port: int,
    expected_command: bytes,
    current_min: float,
    current_max: float,
) -> None:
    # Arrange — many samples to exercise random range boundaries
    ammeter = ammeter_class(port)
    # Act
    results = [ammeter.measure_current() for _ in range(NUM_MEASURE_SAMPLES)]
    # Assert
    out_of_range = [v for v in results if not (current_min <= v <= current_max)]
    assert out_of_range == [], (
        f"{ammeter_class.__name__}.measure_current() produced out-of-range values: {out_of_range}"
    )


# ---------------------------------------------------------------------------
# Parametrized client tests — mocked network I/O (Rule 7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "port, expected_command",
    [
        (CIRCUTOR_PORT, CIRCUTOR_EXPECTED_COMMAND),
        (ENTES_PORT,    ENTES_EXPECTED_COMMAND),
        (GREENLEE_PORT, GREENLEE_EXPECTED_COMMAND),
    ],
    ids=_AMMETER_IDS,
)
@patch("Ammeters.client.socket")
def test_request_current_valid_command_returns_float(
    mock_socket_cls: MagicMock,
    port: int,
    expected_command: bytes,
) -> None:
    # Arrange
    mock_sock = MagicMock()
    mock_socket_cls.return_value.__enter__.return_value = mock_sock
    mock_sock.recv.return_value = str(MOCK_CURRENT_VALUE).encode("utf-8")
    # Act
    result = request_current_from_ammeter(port, expected_command)
    # Assert
    assert result == MOCK_CURRENT_VALUE, (
        f"request_current_from_ammeter must return {MOCK_CURRENT_VALUE} for a valid response; "
        f"got {result!r}"
    )


@pytest.mark.parametrize(
    "port",
    [CIRCUTOR_PORT, ENTES_PORT, GREENLEE_PORT],
    ids=_AMMETER_IDS,
)
@patch("Ammeters.client.socket")
def test_request_current_invalid_command_returns_none_when_no_data(
    mock_socket_cls: MagicMock,
    port: int,
) -> None:
    # Arrange
    mock_sock = MagicMock()
    mock_socket_cls.return_value.__enter__.return_value = mock_sock
    mock_sock.recv.return_value = b""  # server sends nothing for wrong command
    # Act
    result = request_current_from_ammeter(port, INVALID_COMMAND)
    # Assert
    assert result is None, (
        "request_current_from_ammeter must return None when the server sends no data "
        f"(invalid command scenario); got {result!r}"
    )


@pytest.mark.parametrize(
    "port",
    [CIRCUTOR_PORT, ENTES_PORT, GREENLEE_PORT],
    ids=_AMMETER_IDS,
)
@patch("Ammeters.client.socket")
def test_request_current_malformed_response_raises_value_error(
    mock_socket_cls: MagicMock,
    port: int,
) -> None:
    # Arrange
    mock_sock = MagicMock()
    mock_socket_cls.return_value.__enter__.return_value = mock_sock
    mock_sock.recv.return_value = b"ERROR: SENSOR_FAULT_0x7F"
    # Assert
    with pytest.raises(ValueError, match="could not convert"):
        # Act
        request_current_from_ammeter(port, INVALID_COMMAND)


@pytest.mark.parametrize(
    "port",
    [CIRCUTOR_PORT, ENTES_PORT, GREENLEE_PORT],
    ids=_AMMETER_IDS,
)
@patch("Ammeters.client.socket")
def test_request_current_connection_refused_error_condition_propagates(
    mock_socket_cls: MagicMock,
    port: int,
) -> None:
    # Arrange — simulate server unreachable
    mock_sock = MagicMock()
    mock_socket_cls.return_value.__enter__.return_value = mock_sock
    mock_sock.connect.side_effect = ConnectionRefusedError("server not running")
    # Assert
    with pytest.raises(ConnectionRefusedError, match="server not running"):
        # Act
        request_current_from_ammeter(port, INVALID_COMMAND)


# ---------------------------------------------------------------------------
# Pinned boundary tests — Rule 8 + Rule 13: parametrized deterministic min/max
# ---------------------------------------------------------------------------

_BOUNDARY_PARAMS = [
    (
        CircutorAmmeter,
        CIRCUTOR_PORT,
        "Ammeters.Circutor_Ammeter.generate_random_float",
        [CIRCUTOR_BOUNDARY_TIME_STEP_MIN] + [CIRCUTOR_BOUNDARY_VOLTAGE_MIN] * CIRCUTOR_NUM_VOLTAGES,
        CIRCUTOR_BOUNDARY_EXPECTED_MIN,
        "min",
    ),
    (
        CircutorAmmeter,
        CIRCUTOR_PORT,
        "Ammeters.Circutor_Ammeter.generate_random_float",
        [CIRCUTOR_BOUNDARY_TIME_STEP_MAX] + [CIRCUTOR_BOUNDARY_VOLTAGE_MAX] * CIRCUTOR_NUM_VOLTAGES,
        CIRCUTOR_BOUNDARY_EXPECTED_MAX,
        "max",
    ),
    (
        EntesAmmeter,
        ENTES_PORT,
        "Ammeters.Entes_Ammeter.generate_random_float",
        [ENTES_BOUNDARY_FIELD_MIN, ENTES_BOUNDARY_CALIBRATION_MIN],
        ENTES_BOUNDARY_EXPECTED_MIN,
        "min",
    ),
    (
        EntesAmmeter,
        ENTES_PORT,
        "Ammeters.Entes_Ammeter.generate_random_float",
        [ENTES_BOUNDARY_FIELD_MAX, ENTES_BOUNDARY_CALIBRATION_MAX],
        ENTES_BOUNDARY_EXPECTED_MAX,
        "max",
    ),
    (
        GreenleeAmmeter,
        GREENLEE_PORT,
        "Ammeters.Greenlee_Ammeter.generate_random_float",
        [GREENLEE_BOUNDARY_VOLTAGE_MIN, GREENLEE_BOUNDARY_RESISTANCE_MAX],
        GREENLEE_BOUNDARY_EXPECTED_MIN,
        "min",
    ),
    (
        GreenleeAmmeter,
        GREENLEE_PORT,
        "Ammeters.Greenlee_Ammeter.generate_random_float",
        [GREENLEE_BOUNDARY_VOLTAGE_MAX, GREENLEE_BOUNDARY_RESISTANCE_MIN],
        GREENLEE_BOUNDARY_EXPECTED_MAX,
        "max",
    ),
]
_BOUNDARY_IDS = [
    "circutor-min",
    "circutor-max",
    "entes-min",
    "entes-max",
    "greenlee-min",
    "greenlee-max",
]


@pytest.mark.parametrize(
    "ammeter_class, port, patch_target, side_effects, expected, label",
    _BOUNDARY_PARAMS,
    ids=_BOUNDARY_IDS,
)
def test_measure_current_boundary_pinned_values_returns_exact_result(
    ammeter_class: type,
    port: int,
    patch_target: str,
    side_effects: list,
    expected: float,
    label: str,
) -> None:
    # Arrange — instantiate ammeter and pin generate_random_float to boundary values
    ammeter = ammeter_class(port)
    with patch(patch_target, side_effect=side_effects):
        # Act
        result = ammeter.measure_current()
    # Assert
    assert abs(result - expected) < FLOAT_TOLERANCE, (
        f"{ammeter_class.__name__}.measure_current() at {label} boundary must return "
        f"{expected}; got {result}"
    )