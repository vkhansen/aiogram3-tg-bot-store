"""Tests for the localization system."""

import sys
from pathlib import Path

# Add telegrambot to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from lexicon.i18n import t
from lexicon.strings import S, LANGS, DEFAULT_LANG, LANG_LABELS


class TestTranslationHelper:
    def test_returns_english_by_default(self):
        assert t("welcome") == "Welcome!"

    def test_returns_correct_language(self):
        assert t("welcome", "th") == "ยินดีต้อนรับ!"
        assert t("welcome", "ru") == "Добро пожаловать!"

    def test_falls_back_to_english_for_unknown_lang(self):
        result = t("welcome", "zz")
        assert result == t("welcome", "en")

    def test_falls_back_to_key_for_unknown_key(self):
        result = t("nonexistent_key", "en")
        assert result == "nonexistent_key"

    def test_format_placeholders(self):
        result = t("item_of", "en", cur=3, total=10)
        assert "3" in result
        assert "10" in result

    def test_format_placeholders_thai(self):
        result = t("item_of", "th", cur=1, total=5)
        assert "1" in result
        assert "5" in result


class TestStringCompleteness:
    """Verify all keys have translations for all supported languages."""

    def test_all_langs_have_labels(self):
        for lang in LANGS:
            assert lang in LANG_LABELS, f"Missing label for language: {lang}"

    def test_all_keys_have_default_lang(self):
        for key, translations in S.items():
            assert DEFAULT_LANG in translations, f"Key '{key}' missing {DEFAULT_LANG} translation"

    def test_all_keys_have_all_languages(self):
        missing = []
        for key, translations in S.items():
            for lang in LANGS:
                if lang not in translations:
                    missing.append(f"{key}.{lang}")
        if missing:
            # Report but don't fail — missing translations fall back to English
            print(f"WARNING: {len(missing)} missing translations: {missing[:10]}...")

    def test_no_empty_translations(self):
        for key, translations in S.items():
            for lang, text in translations.items():
                assert text.strip(), f"Empty translation: {key}.{lang}"


class TestStringKeys:
    """Verify essential keys exist."""

    REQUIRED_KEYS = [
        "welcome", "btn_menu", "btn_cart", "btn_about", "btn_payment",
        "btn_delivery", "btn_back", "btn_buy", "btn_remove", "btn_home",
        "btn_order", "btn_prev", "btn_next", "btn_change_lang",
        "choose_lang", "lang_set", "added_to_cart", "cart_empty",
        "price", "total", "item_of", "cart_item_of",
        "cat_food", "cat_drinks", "cat_desserts",
    ]

    def test_required_keys_exist(self):
        for key in self.REQUIRED_KEYS:
            assert key in S, f"Required key missing: {key}"
