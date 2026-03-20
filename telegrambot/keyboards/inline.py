from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lexicon.i18n import t
from lexicon.strings import LANGS, LANG_LABELS, S


class MenuCallBack(CallbackData, prefix="menu"):
    level: int
    menu_name: str
    category: int | None = None
    page: int = 1
    product_id: int | None = None


class LangCallBack(CallbackData, prefix="lang"):
    lang: str


LANG_FLAGS = {
    "en": "🇬🇧",
    "th": "🇹🇭",
    "ru": "🇷🇺",
    "uk": "🇺🇦",
    "ar": "🇸🇦",
    "ps": "🇦🇫",
    "fa": "🇮🇷",
}


def get_lang_btns(sizes: tuple[int] = (3,)):
    keyboard = InlineKeyboardBuilder()
    for lang_code in LANGS:
        flag = LANG_FLAGS.get(lang_code, "🌐")
        label = LANG_LABELS.get(lang_code, lang_code)
        keyboard.add(
            InlineKeyboardButton(
                text=f"{flag} {label}",
                callback_data=LangCallBack(lang=lang_code).pack(),
            )
        )
    return keyboard.adjust(*sizes).as_markup()


def get_user_main_btns(*, level: int, lang: str = "en", sizes: tuple[int] = (2,)):
    keyboard = InlineKeyboardBuilder()
    btns = {
        "btn_menu": "catalog",
        "btn_cart": "cart",
        "btn_about": "about",
        "btn_payment": "payment",
        "btn_delivery": "shipping",
        "btn_change_lang": "change_lang",
    }
    for key, menu_name in btns.items():
        text = t(key, lang)
        if menu_name == "catalog":
            keyboard.add(
                InlineKeyboardButton(
                    text=text,
                    callback_data=MenuCallBack(
                        level=level + 1, menu_name=menu_name
                    ).pack(),
                )
            )
        elif menu_name == "cart":
            keyboard.add(
                InlineKeyboardButton(
                    text=text,
                    callback_data=MenuCallBack(level=3, menu_name=menu_name).pack(),
                )
            )
        elif menu_name == "change_lang":
            keyboard.add(
                InlineKeyboardButton(
                    text=text,
                    callback_data=MenuCallBack(level=level, menu_name=menu_name).pack(),
                )
            )
        else:
            keyboard.add(
                InlineKeyboardButton(
                    text=text,
                    callback_data=MenuCallBack(level=level, menu_name=menu_name).pack(),
                )
            )

    return keyboard.adjust(*sizes).as_markup()


def get_user_catalog_btns(*, level: int, categories: list, lang: str = "en", sizes: tuple[int] = (2,)):
    keyboard = InlineKeyboardBuilder()

    keyboard.add(
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=MenuCallBack(level=level - 1, menu_name="main").pack(),
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=t("btn_cart", lang),
            callback_data=MenuCallBack(level=3, menu_name="cart").pack(),
        )
    )

    for c in categories:
        cat_key = f"cat_{c.name.lower()}"
        cat_name = t(cat_key, lang) if cat_key in S else c.name
        keyboard.add(
            InlineKeyboardButton(
                text=cat_name,
                callback_data=MenuCallBack(
                    level=level + 1, menu_name=c.name, category=c.id
                ).pack(),
            )
        )

    return keyboard.adjust(*sizes).as_markup()


def get_products_btns(
    *,
    level: int,
    category: int,
    page: int,
    pagination_btns: dict,
    product_id: int,
    lang: str = "en",
    sizes: tuple[int] = (2, 1)
):
    keyboard = InlineKeyboardBuilder()

    keyboard.add(
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=MenuCallBack(level=level - 1, menu_name="catalog").pack(),
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=t("btn_cart", lang),
            callback_data=MenuCallBack(level=3, menu_name="cart").pack(),
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text=t("btn_buy", lang),
            callback_data=MenuCallBack(
                level=level, menu_name="add_to_cart", product_id=product_id
            ).pack(),
        )
    )

    keyboard.adjust(*sizes)

    row = []
    for text, menu_name in pagination_btns.items():
        if menu_name == "next":
            row.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=MenuCallBack(
                        level=level,
                        menu_name=menu_name,
                        category=category,
                        page=page + 1,
                    ).pack(),
                )
            )

        elif menu_name == "previous":
            row.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=MenuCallBack(
                        level=level,
                        menu_name=menu_name,
                        category=category,
                        page=page - 1,
                    ).pack(),
                )
            )

    return keyboard.row(*row).as_markup()


def get_user_cart(
    *,
    level: int,
    page: int | None,
    pagination_btns: dict | None,
    product_id: int | None,
    lang: str = "en",
    sizes: tuple[int] = (3,)
):
    keyboard = InlineKeyboardBuilder()
    if page:
        keyboard.add(
            InlineKeyboardButton(
                text=t("btn_remove", lang),
                callback_data=MenuCallBack(
                    level=level, menu_name="delete", product_id=product_id, page=page
                ).pack(),
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="-1",
                callback_data=MenuCallBack(
                    level=level, menu_name="decrement", product_id=product_id, page=page
                ).pack(),
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="+1",
                callback_data=MenuCallBack(
                    level=level, menu_name="increment", product_id=product_id, page=page
                ).pack(),
            )
        )

        keyboard.adjust(*sizes)

        row = []
        for text, menu_name in pagination_btns.items():
            if menu_name == "next":
                row.append(
                    InlineKeyboardButton(
                        text=text,
                        callback_data=MenuCallBack(
                            level=level, menu_name=menu_name, page=page + 1
                        ).pack(),
                    )
                )
            elif menu_name == "previous":
                row.append(
                    InlineKeyboardButton(
                        text=text,
                        callback_data=MenuCallBack(
                            level=level, menu_name=menu_name, page=page - 1
                        ).pack(),
                    )
                )

        keyboard.row(*row)

        row2 = [
            InlineKeyboardButton(
                text=t("btn_home", lang),
                callback_data=MenuCallBack(level=0, menu_name="main").pack(),
            ),
            InlineKeyboardButton(
                text=t("btn_order", lang),
                callback_data=MenuCallBack(level=0, menu_name="order").pack(),
            ),
        ]
        return keyboard.row(*row2).as_markup()
    else:
        keyboard.add(
            InlineKeyboardButton(
                text=t("btn_home", lang),
                callback_data=MenuCallBack(level=0, menu_name="main").pack(),
            )
        )

        return keyboard.adjust(*sizes).as_markup()


def get_callback_btns(*, btns: dict[str, str], sizes: tuple[int] = (2,)):
    keyboard = InlineKeyboardBuilder()

    for text, data in btns.items():
        keyboard.add(InlineKeyboardButton(text=text, callback_data=data))

    return keyboard.adjust(*sizes).as_markup()
