from analog_meter_reader.prompt import build_default_prompt

# Dokładny tekst poprzedniego, sztywnego DEFAULT_PROMPT (sprzed obsługi
# konfigurowalnych kolorów) - build_default_prompt("black", "red") musi
# wygenerować identyczny prompt, inaczej to cicha zmiana zachowania AI dla
# każdego, kto nie ustawił własnych kolorów (czyli prawie każdego).
_ORIGINAL_HARDCODED_PROMPT = (
    "This is a photo of a utility meter's digit strip. Black digits on the "
    "drums show the whole units (the integer part), red digits show the "
    "fractional part and may look blurry - that's normal, always give your "
    "best guess for the red digits, never refuse because of them. "
    "Reply ONLY with a number in the format XXX.XXX (dot as separator), no "
    "other text. Reply UNCERTAIN only if the BLACK digits (whole "
    "units) are unreadable."
)


def test_default_colors_match_original_hardcoded_prompt():
    assert build_default_prompt("black", "red") == _ORIGINAL_HARDCODED_PROMPT


def test_custom_colors_are_substituted():
    prompt = build_default_prompt("white", "blue")
    assert "White digits on the drums" in prompt
    assert "blue digits show the fractional part" in prompt
    assert "best guess for the blue digits" in prompt
    assert "only if the WHITE digits" in prompt
    assert "black" not in prompt.lower()
    assert "red" not in prompt.lower()


def test_color_capitalization_is_normalized_regardless_of_input_case():
    prompt = build_default_prompt("BLACK", "Red")
    assert "Black digits on the drums" in prompt
    assert "only if the BLACK digits" in prompt
    assert "Red digits show the fractional part" in prompt
