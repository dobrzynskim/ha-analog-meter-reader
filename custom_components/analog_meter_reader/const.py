"""Stałe dla integracji Analog Meter Reader."""

DOMAIN = "analog_meter_reader"
STORAGE_VERSION = 1

CONF_NAME = "name"
CONF_CAMERA_URL = "camera_url"
CONF_CAMERA_ENTITY_ID = "camera_entity_id"
CONF_AI_PROVIDER = "ai_provider"
CONF_API_KEY = "api_key"
CONF_API_BASE_URL = "api_base_url"
CONF_AI_MODEL = "ai_model"
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
CONF_WHOLE_DIGIT_COLOR = "whole_digit_color"
CONF_FRACTION_DIGIT_COLOR = "fraction_digit_color"
CONF_CONFIRM = "confirm"
CONF_QUIET_HOURS_START = "quiet_hours_start"
CONF_QUIET_HOURS_END = "quiet_hours_end"
CONF_GEMINI_MODEL = "gemini_model"  # legacy klucz opcji sprzed obsługi wielu dostawców - patrz CONF_AI_MODEL

# Dostawcy AI obsługiwani przez api.py. "openai_compatible" pokrywa zarówno
# sam OpenAI, jak i dowolny self-hosted model wystawiający zgodne API
# (Ollama, LM Studio, vLLM, text-generation-webui...) - to jest właśnie
# "swój model" z punktu widzenia użytkownika.
AI_PROVIDER_GEMINI = "gemini"
AI_PROVIDER_ANTHROPIC = "anthropic"
AI_PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
AI_PROVIDERS = [AI_PROVIDER_GEMINI, AI_PROVIDER_ANTHROPIC, AI_PROVIDER_OPENAI_COMPATIBLE]
DEFAULT_AI_PROVIDER = AI_PROVIDER_GEMINI

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

# Krótki retry z backoffem na przejściowe błędy zapytania do AI (timeout,
# zerwane połączenie, HTTP 429/5xx - patrz api.MeterReaderApiError.retryable)
# - jeden dodatkowy strzał w tym samym cyklu zamiast czekania na kolejny,
# pełny scan_interval (typowo kilka-kilkanaście minut). Błędy nie-przejściowe
# (zły klucz, model nie istnieje) nie są ponawiane w ogóle.
AI_RETRY_ATTEMPTS = 2
AI_RETRY_BACKOFF_SECONDS = 5

# Model konfigurowalny (Options Flow, CONF_GEMINI_MODEL) - to wartość
# domyślna, nie sztywna. Google regularnie wycofuje starsze modele dla
# nowych kluczy (patrz historia tego repo: gemini-2.5-flash przestał działać
# z dnia na dzień z HTTP 404 "no longer available to new users") - sztywne
# wpisanie jednej nazwy w kodzie gwarantuje, że kiedyś się to powtórzy.
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

# Domyślny model per dostawca, używany gdy CONF_AI_MODEL jest puste. Dla
# "openai_compatible" celowo brak sensownego uniwersalnego domyślnego modelu
# (self-hosted serwery same decydują, jaki model mają wgrany) - pusty string
# oznacza "wyślij bez pola model / niech serwer użyje swojego domyślnego".
DEFAULT_MODEL_BY_PROVIDER = {
    AI_PROVIDER_GEMINI: DEFAULT_GEMINI_MODEL,
    AI_PROVIDER_ANTHROPIC: "claude-sonnet-5",
    AI_PROVIDER_OPENAI_COMPATIBLE: "",
}

# Kolory cyfr - większość liczników wody/gazu ma czarne cyfry pełnych
# jednostek i czerwone cyfry ułamka na osobnym, wyróżnionym bębenku, ale to
# tylko najpopularniejszy układ, nie jedyny (patrz CONF_WHOLE_DIGIT_COLOR/
# CONF_FRACTION_DIGIT_COLOR w Options Flow - konfigurowalne per licznik).
DEFAULT_WHOLE_DIGIT_COLOR = "black"
DEFAULT_FRACTION_DIGIT_COLOR = "red"

# Szablon domyślnego promptu - prompt.build_default_prompt() wypełnia go
# kolorami z konfiguracji (domyślnie czarny/czerwony, jak wyżej). Przy tych
# wartościach domyślnych daje dokładnie ten sam tekst, co poprzednia,
# sztywna wersja tego promptu - patrz tests/test_prompt.py.
DEFAULT_PROMPT_TEMPLATE = (
    "This is a photo of a utility meter's digit strip. {whole_color} digits on the "
    "drums show the whole units (the integer part), {fraction_color} digits show the "
    "fractional part and may look blurry - that's normal, always give your "
    "best guess for the {fraction_color} digits, never refuse because of them. "
    "Reply ONLY with a number in the format XXX.XXX (dot as separator), no "
    "other text. Reply {uncertain_marker} only if the {whole_color_upper} digits (whole "
    "units) are unreadable."
)
UNCERTAIN_MARKER = "UNCERTAIN"
