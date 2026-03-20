from lexicon.strings import S, DEFAULT_LANG


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """Get translated string. Falls back to default language, then to key name."""
    text = S.get(key, {}).get(lang) or S.get(key, {}).get(DEFAULT_LANG, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
