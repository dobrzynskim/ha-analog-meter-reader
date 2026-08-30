"""Stałe dla integracji Analog Meter Reader."""

DOMAIN = "analog_meter_reader"
STORAGE_VERSION = 1

CONF_NAME = "name"
CONF_CAMERA_URL = "camera_url"
CONF_CAMERA_ENTITY_ID = "camera_entity_id"
CONF_API_KEY = "api_key"
CONF_FLIP_HORIZONTAL = "flip_horizontal"
CONF_CROP_LEFT = "crop_left"
CONF_CROP_TOP = "crop_top"
CONF_CROP_RIGHT = "crop_right"
CONF_CROP_BOTTOM = "crop_bottom"
CONF_DEVICE_CLASS = "device_class"
CONF_UNIT_OF_MEASUREMENT = "unit_of_measurement"
CONF_MAX_STEP = "max_step"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
CONF_PROMPT = "prompt"
CONF_CONFIRM = "confirm"
CONF_QUIET_HOURS_START = "quiet_hours_start"
CONF_QUIET_HOURS_END = "quiet_hours_end"

DEFAULT_FLIP_HORIZONTAL = True
DEFAULT_DEVICE_CLASS = "water"
DEFAULT_UNIT_OF_MEASUREMENT = "m³"
DEFAULT_MAX_STEP = 2.0
DEFAULT_SCAN_INTERVAL_MINUTES = 10
CROP_UPSCALE_FACTOR = 4

# Ile kolejnych cykli pod rząd z odrzuconym/niepewnym odczytem, zanim zgłosimy
# Repair Issue sugerujący, że kamera się poruszyła i ramka wymaga ponownej
# kalibracji - kilka pojedynczych złych odczytów to normalny szum (patrz
# validation.py), dopiero DŁUGA seria oznacza realny problem ze źródłem.
CALIBRATION_DRIFT_ISSUE = "calibration_drift"
CONSECUTIVE_BAD_THRESHOLD = 6

GEMINI_MODEL = "gemini-3.6-flash"

# Domyślny prompt dopasowany do liczników z czarnymi cyframi (pełne jednostki)
# i czerwonymi cyframi (ułamek jednostki) na bębenkach - typowy układ liczników
# wody/gazu. Nadpisywalny w Options Flow dla innych typów liczników.
DEFAULT_PROMPT = (
    "This is a photo of a utility meter's digit strip. Black digits on the "
    "drums show the whole units (the integer part), red digits show the "
    "fractional part and may look blurry - that's normal, always give your "
    "best guess for the red digits, never refuse because of them. "
    "Reply ONLY with a number in the format XXX.XXX (dot as separator), no "
    "other text. Reply {uncertain_marker} only if the BLACK digits (whole "
    "units) are unreadable."
)
UNCERTAIN_MARKER = "UNCERTAIN"
