from aiogram.types import InputMediaPhoto, FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession

import os

from lexicon.i18n import t
from lexicon.strings import S

PLACEHOLDER_IMAGE = os.path.join(os.path.dirname(__file__), "..", "assets", "placeholder.png")

from database.orm_query import (
    orm_add_to_cart,
    orm_delete_from_cart,
    orm_get_banner,
    orm_get_categories,
    orm_get_products,
    orm_get_user_carts,
    orm_reduce_product_in_cart,
)
from keyboards.inline import (
    get_products_btns,
    get_user_cart,
    get_user_catalog_btns,
    get_user_main_btns,
)

from utils.paginator import Paginator


def _banner_text(banner_name: str, lang: str) -> str:
    """Get localized banner text. Falls back to DB description."""
    key_map = {
        "main": "welcome",
        "about": "about_text",
        "payment": "payment_text",
        "shipping": "shipping_text",
        "catalog": "categories",
        "cart": "cart_empty",
    }
    key = key_map.get(banner_name)
    if key and key in S:
        return t(key, lang)
    return ""


async def main_menu(session, level, menu_name, lang="en"):
    banner = await orm_get_banner(session, menu_name)
    media = banner.image if banner.image else FSInputFile(PLACEHOLDER_IMAGE)
    caption = _banner_text(menu_name, lang)
    image = InputMediaPhoto(media=media, caption=caption)

    kbds = get_user_main_btns(level=level, lang=lang)

    return image, kbds


async def catalog(session, level, menu_name, lang="en"):
    banner = await orm_get_banner(session, menu_name)
    media = banner.image if banner.image else FSInputFile(PLACEHOLDER_IMAGE)
    caption = _banner_text("catalog", lang)
    image = InputMediaPhoto(media=media, caption=caption)

    categories = await orm_get_categories(session)
    kbds = get_user_catalog_btns(level=level, categories=categories, lang=lang)

    return image, kbds


def pages(paginator: Paginator, lang: str = "en"):
    btns = dict()
    if paginator.has_previous():
        btns[t("btn_prev", lang)] = "previous"

    if paginator.has_next():
        btns[t("btn_next", lang)] = "next"

    return btns


async def products(session, level, category, page, lang="en"):
    products = await orm_get_products(session, category_id=category)

    paginator = Paginator(products, page=page)
    product = paginator.get_page()[0]

    image = InputMediaPhoto(
        media=product.image,
        caption=f"<strong>{product.name}</strong>\n{product.description}\n"
                f"{t('price', lang)}: {round(product.price, 2)}฿\n"
                f"<strong>{t('item_of', lang, cur=paginator.page, total=paginator.pages)}</strong>",
    )

    pagination_btns = pages(paginator, lang)

    kbds = get_products_btns(
        level=level,
        category=category,
        page=page,
        pagination_btns=pagination_btns,
        product_id=product.id,
        lang=lang,
    )

    return image, kbds


async def carts(session, level, menu_name, page, user_id, product_id, lang="en"):
    if menu_name == "delete":
        await orm_delete_from_cart(session, user_id, product_id)
        if page > 1:
            page -= 1
    elif menu_name == "decrement":
        is_cart = await orm_reduce_product_in_cart(session, user_id, product_id)
        if page > 1 and not is_cart:
            page -= 1
    elif menu_name == "increment":
        await orm_add_to_cart(session, user_id, product_id)

    carts = await orm_get_user_carts(session, user_id)

    if not carts:
        banner = await orm_get_banner(session, "cart")
        cart_media = banner.image if banner.image else FSInputFile(PLACEHOLDER_IMAGE)
        image = InputMediaPhoto(
            media=cart_media, caption=f"<strong>{t('cart_empty', lang)}</strong>"
        )

        kbds = get_user_cart(
            level=level,
            page=None,
            pagination_btns=None,
            product_id=None,
            lang=lang,
        )

    else:
        paginator = Paginator(carts, page=page)

        cart = paginator.get_page()[0]

        cart_price = round(cart.quantity * cart.product.price, 2)
        total_price = round(
            sum(cart.quantity * cart.product.price for cart in carts), 2
        )
        image = InputMediaPhoto(
            media=cart.product.image,
            caption=f"<strong>{cart.product.name}</strong>\n{cart.product.price}฿ x {cart.quantity} = {cart_price}฿\n"
                    f"{t('cart_item_of', lang, cur=paginator.page, total=paginator.pages)}\n"
                    f"{t('total', lang)}: {total_price}฿",
        )

        pagination_btns = pages(paginator, lang)

        kbds = get_user_cart(
            level=level,
            page=page,
            pagination_btns=pagination_btns,
            product_id=cart.product.id,
            lang=lang,
        )

    return image, kbds


async def get_menu_content(
    session: AsyncSession,
    level: int,
    menu_name: str,
    category: int | None = None,
    page: int | None = None,
    product_id: int | None = None,
    user_id: int | None = None,
    lang: str = "en",
):
    if level == 0:
        return await main_menu(session, level, menu_name, lang)
    elif level == 1:
        return await catalog(session, level, menu_name, lang)
    elif level == 2:
        return await products(session, level, category, page, lang)
    elif level == 3:
        return await carts(session, level, menu_name, page, user_id, product_id, lang)
