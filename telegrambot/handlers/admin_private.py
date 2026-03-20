from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_change_banner_image,
    orm_get_categories,
    orm_add_product,
    orm_delete_product,
    orm_get_info_pages,
    orm_get_product,
    orm_get_products,
    orm_get_user_lang,
    orm_update_product,
)

from filters.chat_types import ChatTypeFilter, IsAdmin

from keyboards.inline import get_callback_btns
from keyboards.reply import get_keyboard
from lexicon.i18n import t


admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())


def get_admin_kb(lang: str = "en"):
    return get_keyboard(
        t("add_product", lang),
        t("products", lang),
        t("add_edit_banner", lang),
        placeholder=t("admin_what", lang),
        sizes=(2,),
    )


@admin_router.message(Command("admin"))
async def admin_features(message: types.Message, session: AsyncSession):
    lang = await orm_get_user_lang(session, message.from_user.id)
    await message.answer(t("admin_what", lang), reply_markup=get_admin_kb(lang))


@admin_router.message(F.text.in_({t("products", l) for l in ["en", "th", "ru", "uk", "ar", "ps", "fa"]}))
async def admin_products(message: types.Message, session: AsyncSession):
    lang = await orm_get_user_lang(session, message.from_user.id)
    categories = await orm_get_categories(session)
    btns = {category.name: f"category_{category.id}" for category in categories}
    await message.answer(
        t("choose_cat", lang), reply_markup=get_callback_btns(btns=btns)
    )


@admin_router.callback_query(F.data.startswith("category_"))
async def starring_at_product(callback: types.CallbackQuery, session: AsyncSession):
    lang = await orm_get_user_lang(session, callback.from_user.id)
    category_id = callback.data.split("_")[-1]
    for product in await orm_get_products(session, int(category_id)):
        await callback.message.answer_photo(
            product.image,
            caption=f"<strong>{product.name}</strong>\n{product.description}\n"
                    f"{t('price', lang)}: {round(product.price, 2)}",
            reply_markup=get_callback_btns(
                btns={
                    t("btn_delete", lang): f"delete_{product.id}",
                    t("btn_edit", lang): f"change_{product.id}",
                },
                sizes=(2,),
            ),
        )
    await callback.answer()
    await callback.message.answer(t("product_list", lang))


@admin_router.callback_query(F.data.startswith("delete_"))
async def delete_product_callback(callback: types.CallbackQuery, session: AsyncSession):
    lang = await orm_get_user_lang(session, callback.from_user.id)
    product_id = callback.data.split("_")[-1]
    await orm_delete_product(session, int(product_id))

    await callback.answer(t("product_deleted", lang))
    await callback.message.answer(t("product_deleted", lang))


class AddBanner(StatesGroup):
    image = State()


@admin_router.message(StateFilter(None), F.text.in_({t("add_edit_banner", l) for l in ["en", "th", "ru", "uk", "ar", "ps", "fa"]}))
async def add_image2(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await orm_get_user_lang(session, message.from_user.id)
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    await message.answer(t("send_banner", lang, pages=", ".join(pages_names)))
    await state.set_state(AddBanner.image)
    await state.update_data(lang=lang)


@admin_router.message(AddBanner.image, F.photo)
async def add_banner(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    lang = data.get("lang", "en")
    image_id = message.photo[-1].file_id
    for_page = message.caption.strip()
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    if for_page not in pages_names:
        await message.answer(t("invalid_page", lang, pages=", ".join(pages_names)))
        return
    await orm_change_banner_image(session, for_page, image_id)
    await message.answer(t("banner_updated", lang))
    await state.clear()


@admin_router.message(AddBanner.image)
async def add_banner2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "en")
    await message.answer(t("send_banner_photo", lang))


class AddProduct(StatesGroup):
    name = State()
    description = State()
    category = State()
    price = State()
    image = State()

    product_for_change = None

    texts = {
        "AddProduct:name": "step_name",
        "AddProduct:description": "step_desc",
        "AddProduct:category": "step_cat",
        "AddProduct:price": "step_price",
        "AddProduct:image": "step_image",
    }


@admin_router.callback_query(StateFilter(None), F.data.startswith("change_"))
async def change_product_callback(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    lang = await orm_get_user_lang(session, callback.from_user.id)
    product_id = callback.data.split("_")[-1]

    product_for_change = await orm_get_product(session, int(product_id))
    AddProduct.product_for_change = product_for_change

    await callback.answer()
    await callback.message.answer(
        t("enter_name", lang), reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AddProduct.name)
    await state.update_data(lang=lang)


@admin_router.message(StateFilter(None), F.text.in_({t("add_product", l) for l in ["en", "th", "ru", "uk", "ar", "ps", "fa"]}))
async def add_product(message: types.Message, state: FSMContext, session: AsyncSession):
    lang = await orm_get_user_lang(session, message.from_user.id)
    await message.answer(
        t("enter_name", lang), reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(AddProduct.name)
    await state.update_data(lang=lang)


@admin_router.message(StateFilter("*"), Command("cancel"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "cancel")
async def cancel_handler(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return
    if AddProduct.product_for_change:
        AddProduct.product_for_change = None
    lang = await orm_get_user_lang(session, message.from_user.id)
    await state.clear()
    await message.answer(t("cancelled", lang), reply_markup=get_admin_kb(lang))


@admin_router.message(StateFilter("*"), Command("back"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "back")
async def back_step_handler(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    current_state = await state.get_state()
    lang = await orm_get_user_lang(session, message.from_user.id)

    if current_state == AddProduct.name:
        await message.answer(t("no_prev_step", lang))
        return

    previous = None
    for step in AddProduct.__all_states__:
        if step.state == current_state:
            await state.set_state(previous)
            step_key = AddProduct.texts.get(previous.state, "step_name")
            await message.answer(
                f"{t('back_to_step', lang)}\n{t(step_key, lang)}"
            )
            return
        previous = step


@admin_router.message(AddProduct.name, F.text)
async def add_name(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    lang = data.get("lang", "en")
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(name=AddProduct.product_for_change.name)
    else:
        if 4 >= len(message.text) >= 150:
            await message.answer(t("name_invalid_len", lang))
            return

        await state.update_data(name=message.text)
    await message.answer(t("enter_desc", lang))
    await state.set_state(AddProduct.description)


@admin_router.message(AddProduct.name)
async def add_name2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "en")
    await message.answer(t("invalid_text", lang))


@admin_router.message(AddProduct.description, F.text)
async def add_description(
    message: types.Message, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    lang = data.get("lang", "en")
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(description=AddProduct.product_for_change.description)
    else:
        if 4 >= len(message.text):
            await message.answer(t("desc_too_short", lang))
            return
        await state.update_data(description=message.text)

    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}
    await message.answer(
        t("choose_cat", lang), reply_markup=get_callback_btns(btns=btns)
    )
    await state.set_state(AddProduct.category)


@admin_router.message(AddProduct.description)
async def add_description2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "en")
    await message.answer(t("invalid_text", lang))


@admin_router.callback_query(AddProduct.category)
async def category_choice(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    data = await state.get_data()
    lang = data.get("lang", "en")
    if int(callback.data) in [
        category.id for category in await orm_get_categories(session)
    ]:
        await callback.answer()
        await state.update_data(category=callback.data)
        await callback.message.answer(t("enter_price", lang))
        await state.set_state(AddProduct.price)
    else:
        await callback.message.answer(t("choose_cat_btn", lang))
        await callback.answer()


@admin_router.message(AddProduct.category)
async def category_choice2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "en")
    await message.answer(t("choose_cat_btn", lang))


@admin_router.message(AddProduct.price, F.text)
async def add_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "en")
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(price=AddProduct.product_for_change.price)
    else:
        try:
            float(message.text)
        except ValueError:
            await message.answer(t("invalid_price", lang))
            return

        await state.update_data(price=message.text)
    await message.answer(t("upload_image", lang))
    await state.set_state(AddProduct.image)


@admin_router.message(AddProduct.price)
async def add_price2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "en")
    await message.answer(t("invalid_price", lang))


@admin_router.message(AddProduct.image, or_f(F.photo, F.text == "."))
async def add_image(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    lang = data.get("lang", "en")
    if message.text and message.text == "." and AddProduct.product_for_change:
        await state.update_data(image=AddProduct.product_for_change.image)

    elif message.photo:
        await state.update_data(image=message.photo[-1].file_id)
    else:
        await message.answer(t("send_photo", lang))
        return
    data = await state.get_data()
    try:
        if AddProduct.product_for_change:
            await orm_update_product(session, AddProduct.product_for_change.id, data)
        else:
            await orm_add_product(session, data)
        await message.answer(t("product_added", lang), reply_markup=get_admin_kb(lang))
        await state.clear()

    except Exception as e:
        await message.answer(
            t("error", lang, err=str(e)),
            reply_markup=get_admin_kb(lang),
        )
        await state.clear()

    AddProduct.product_for_change = None


@admin_router.message(AddProduct.image)
async def add_image2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "en")
    await message.answer(t("send_photo", lang))
