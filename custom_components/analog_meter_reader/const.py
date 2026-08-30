"""Stałe dla integracji Analog Meter Reader."""

DOMAIN = "analog_meter_reader"
STORAGE_VERSION = 1

CONF_NAME = "name"
CONF_CAMERA_URL = "camera_url"
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

DEFAULT_FLIP_HORIZONTAL = True
DEFAULT_DEVICE_CLASS = "water"
DEFAULT_UNIT_OF_MEASUREMENT = "m³"
DEFAULT_MAX_STEP = 2.0
DEFAULT_SCAN_INTERVAL_MINUTES = 10
CROP_UPSCALE_FACTOR = 4

GEMINI_MODEL = "gemini-2.5-flash"

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
