import asyncio
import yaml
from aiogram import Bot
from datetime import datetime
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
SLEEP_TIMER_SECS = 300

RETROSPECTIVE_SEARCH_AGENT_COUNT = 5
RETROSPECTIVE_SEARCH_AGENT_SLEEP_TIMER = 0.3

bot = Bot(token=API_TOKEN, proxy=PROXY_URL)


def output_log(message, level="INFO"):
    n = datetime.now()
    ns = n.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ns} " + f"[{level.upper()}".ljust(10, " ") + f"] {message}")


async def notify_users():
    output_log("Starting notification process")
    apps = db.get_not_notified_apps()
    tasks = list()
    app_ids = list()
    async for app in apps:
        output_log(f"New app {app['name']} found")
        users = db.get_users_by_developer(app["author"].lower())
        text = "New app {name} from {author} released for {countries}:\n{link}".format(**app)
        users_to_notify = 0
        async for u in users:
            if u['active']:
                tasks.append(
                    asyncio.create_task(bot.send_message(u["cid"], text))
                )
                users_to_notify += 1
        output_log(f"Found {users_to_notify} users for this app")
        app_ids.append(app['_id'])

    if tasks:
        output_log("Sending notifications")
        await asyncio.gather(*tasks)
        output_log("Notifications done")
    else:
        output_log("No notifications should be done")
    if app_ids:
        output_log("Marking apps as notified")
        await asyncio.gather(*[asyncio.create_task(db.change_app_notification_status(app_id, True)) for app_id in app_ids])
        output_log("Marking apps as notified done")


async def start_notifier():
    output_log("Starting cycle")
    while True:
        await notify_users()
        output_log(f"Sleeping for {SLEEP_TIMER_SECS} seconds")
        await asyncio.sleep(SLEEP_TIMER_SECS)


async def start_retrospective_search_agent(agent_id: int):
    output_log(f"Starting retrospective search agent (agent_id: {agent_id})")
    while True:
        task = await db.get_rsearch_task()
        if task:
            cid = task['cid']
            output_log(f"Task found for cid {cid} (agent_id: {agent_id})")
            dev = await db.get_user_last_developer(cid)
            if dev:
                dev = dev[0]
                apps = db.search_apps_by_dev(dev)
                send_task = []
                async for app in apps:
                    text = "New app {name} from {author} released for {countries}:\n{link}".format(**app)
                    send_task.append(asyncio.create_task(bot.send_message(cid, text)))

        await asyncio.sleep(RETROSPECTIVE_SEARCH_AGENT_SLEEP_TIMER)


if __name__ == "__main__":
    sleep(5)
    loop = asyncio.get_event_loop()
    for i in range(RETROSPECTIVE_SEARCH_AGENT_COUNT):
        loop.create_task(start_retrospective_search_agent(i))
    loop.create_task(start_notifier())
    try:
        loop.run_forever()
    finally:
        loop.close()
