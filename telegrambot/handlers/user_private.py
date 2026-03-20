from aiogram import Router, types
from aiogram.filters import CommandStart
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_to_cart,
    orm_add_user,
    orm_get_user,
    orm_get_user_lang,
    orm_set_user_lang,
)
from filters.chat_types import ChatTypeFilter
from handlers.menu_processing import get_menu_content
from keyboards.inline import LangCallBack, MenuCallBack, get_lang_btns
from lexicon.i18n import t

user_private_router = Router()
user_private_router.message.filter(ChatTypeFilter(["private"]))


@user_private_router.message(CommandStart())
async def start_cmd(message: types.Message, session: AsyncSession):
    user = await orm_get_user(session, message.from_user.id)
    if user is None:
        # New user — show language picker
        await orm_add_user(
            session,
            user_id=message.from_user.id,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            phone=None,
        )
        await message.answer(
            "🌐 Choose your language / เลือกภาษา / Выберите язык / اختر لغتك",
            reply_markup=get_lang_btns(),
        )
        return

    lang = user.lang
    media, reply_markup = await get_menu_content(session, level=0, menu_name="main", lang=lang)

    await message.answer_photo(
        media.media, caption=media.caption, reply_markup=reply_markup
    )


@user_private_router.callback_query(LangCallBack.filter())
async def lang_chosen(
    callback: types.CallbackQuery, callback_data: LangCallBack, session: AsyncSession
):
    lang = callback_data.lang
    user = await orm_get_user(session, callback.from_user.id)
    if user is None:
        await orm_add_user(
            session,
            user_id=callback.from_user.id,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            phone=None,
            lang=lang,
        )
    else:
        await orm_set_user_lang(session, callback.from_user.id, lang)

    await callback.answer(t("lang_set", lang))

    media, reply_markup = await get_menu_content(session, level=0, menu_name="main", lang=lang)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer_photo(
        media.media, caption=media.caption, reply_markup=reply_markup
    )


async def add_to_cart(
    callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession
):
    user = callback.from_user
    lang = await orm_get_user_lang(session, user.id)
    await orm_add_user(
        session,
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=None,
    )
    await orm_add_to_cart(session, user_id=user.id, product_id=callback_data.product_id)
    await callback.answer(t("added_to_cart", lang))


@user_private_router.callback_query(MenuCallBack.filter())
async def user_menu(
    callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession
):
    lang = await orm_get_user_lang(session, callback.from_user.id)

    if callback_data.menu_name == "add_to_cart":
        await add_to_cart(callback, callback_data, session)
        return

    if callback_data.menu_name == "change_lang":
        await callback.message.delete()
        await callback.message.answer(
            t("choose_lang", lang),
            reply_markup=get_lang_btns(),
        )
        await callback.answer()
        return

    media, reply_markup = await get_menu_content(
        session,
        level=callback_data.level,
        menu_name=callback_data.menu_name,
        category=callback_data.category,
        page=callback_data.page,
        product_id=callback_data.product_id,
        user_id=callback.from_user.id,
        lang=lang,
    )

    await callback.message.edit_media(media=media, reply_markup=reply_markup)
    await callback.answer()
