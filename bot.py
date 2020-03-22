import asyncio
import logging
import pymongo.errors
import yaml

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher.filters.state import State, StatesGroup
from time import sleep

import database as db

SECRETS_FILE = "secrets/credentials.yml"
with open(SECRETS_FILE) as file:
    secrets = yaml.safe_load(file)


PROXY_HOST = secrets["proxy_host"]
PROXY_PORT = secrets["proxy_port"]
PROXY_USER = secrets["proxy_user"]
PROXY_PASS = secrets["proxy_pass"]
PROXY_PROTO = "socks5"
PROXY_URL = f"{PROXY_PROTO}://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

API_TOKEN = secrets["api_token"]


HELLO_MESSAGE = """
Hello! I am Storeglide reporter. Please use /register for start.
Commands:
/help - show this message
/register - register for notifications
/add %DEVELOPER% - add developer to notifications
/del %DEVELOPER% - delete developer from notifications
/del - delete developer (choose from buttons)
/list - list of developers configured for notification
/search %DEVELOPER% - search for apps by developer in last 5 days cache
/start - show this message
/stop - unregister for notifications
"""
REGISTERED_MESSAGE = """
Registered for notifications.
Use /add %DEVELOPER% to add developer for your notifications.
"""
STOP_MESSAGE = """
Notifications stopped.
"""

RETROSEARCH_SKIP = 0
RETROSEARCH_LIMIT = 5



# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN, proxy=PROXY_URL)
dp = Dispatcher(bot)


class Form(StatesGroup):
    dev = State()


@dp.message_handler(commands=['start', 'help'])
async def start_handler(message: types.Message):
    await message.answer(HELLO_MESSAGE)


@dp.message_handler(commands=['register'])
async def register_handler(message: types.Message):
    try:
        await db.create_user(message.chat.id)
    except pymongo.errors.DuplicateKeyError:
        await db.change_user_status(message.chat.id, active=True)
    await message.answer(REGISTERED_MESSAGE)


@dp.message_handler(commands=['stop'])
async def stop_handler(message: types.Message):
    await db.change_user_status(message.chat.id, active=False)
    await message.answer(STOP_MESSAGE)


@dp.message_handler(commands=['add'])
async def add_handler(message: types.Message):
    message_text = message.text
    message_text = message_text.strip()
    message_text = message_text.split()
    if len(message_text) < 2:
        await message.answer("You need to specify developer")
        return None

    dev = ' '.join(message_text[1:])
    try:
        await db.add_developer(message.chat.id, dev.lower())
    except pymongo.errors.DuplicateKeyError:
        text = f"{dev} already added"
    else:
        text = "Done"

    await message.answer(text)
    if dev not in text:
        callback_data = f"rsrch__"
        markup = types.InlineKeyboardMarkup()
        button = types.InlineKeyboardButton(
            text="Yes", callback_data=callback_data
        )
        markup.add(button)
        await message.answer("Want to start retrospective search?", reply_markup=markup)


@dp.message_handler(commands=['del'])
async def del_handler(message: types.Message):
    message_text = message.text.split()
    if len(message_text) < 2:
        devs = sorted(await db.get_developers(message.chat.id))
        if devs:
            markup = types.InlineKeyboardMarkup()
            keyboard = [
                types.inline_keyboard.InlineKeyboardButton(
                    text=d, callback_data=f"devtodel__{devs.index(d)}") for d in devs
            ]
            markup.add(*keyboard)
            await message.answer("Choose dev to del:", reply_markup=markup)

        else:
            await message.answer("Nothing to delete")

        return None
    dev = message_text[1]
    await db.del_developer(message.chat.id, dev)
    text = "Done"

    await message.answer(text)


@dp.message_handler(commands=['list'])
async def list_handler(message: types.Message):
    devs = sorted(await db.get_developers(message.chat.id))
    devs = '\n'.join(devs)
    text = "Your developers notification list:\n\n" + devs

    await message.answer(text)


@dp.message_handler(commands=['search'])
async def search_handler(message: types.Message):
    message_text = message.text
    message_text = message_text.strip()
    message_text = message_text.split()
    if len(message_text) < 2:
        await message.answer("You need to specify developer")
        return None

    dev = ' '.join(message_text[1:])
    apps = db.search_apps_by_dev(dev)
    found_flag = False
    async for app in apps:
        text = "Found at {created}. App {name} from {author} released for {countries}:\n{link}".format(**app)
        await message.answer(text)
        found_flag = True

    if not found_flag:
        text = "Nothing found"
        await message.answer(text)


@dp.callback_query_handler(lambda callback_query: "devtodel__" in callback_query.data)
async def delete_dev_callback_query(callback_query: types.CallbackQuery):
    index = int(callback_query.data.split("__")[1])
    devs = sorted(await db.get_developers(callback_query.message.chat.id))
    dev = devs[index]
    text = f"Your choice is:\n {dev}"
    await callback_query.message.edit_text(text)
    await db.del_developer(callback_query.message.chat.id, dev)
    await callback_query.message.reply("Deleted")


@dp.callback_query_handler(lambda callback_query: "rsrch__" in callback_query.data)
async def retro_search_callback_query(callback_query: types.CallbackQuery):
    text = "Searching..."
    search_task = {
        "type": "rsearch",
        "cid": callback_query.message.chat.id,
    }
    await asyncio.gather(
        asyncio.create_task(callback_query.message.edit_text(text)),
        asyncio.create_task(db.insert_task(search_task))
    )


if __name__ == '__main__':
    sleep(7)
    executor.start_polling(dp, skip_updates=True)
