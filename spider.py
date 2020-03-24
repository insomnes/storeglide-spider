import asyncio
import signal
import json
from aiohttp import ClientSession
from aiohttp_socks import ProxyConnector
from bs4 import BeautifulSoup
from datetime import datetime
from time import sleep
from typing import Dict, List

import database as db

SECRETS_FILE = "secrets/http_proxy.json"
with open(SECRETS_FILE) as file:
    secrets = json.loads(file)

PROXY_HOST = secrets["proxy_host"]
PROXY_PORT = secrets["proxy_port"]
PROXY_USER = secrets["proxy_user"]
PROXY_PASS = secrets["proxy_pass"]
PROXY_PROTO = "socks5"
PROXY_URL = f"{PROXY_PROTO}://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"


AppList = List[Dict[str, str]]

STOREGLIDE_URL = "https://store.storeglide.com/"
STOREGLIDE_PAGES_DEEP = 10
SLEEP_TIMER_SECS = 300


def output_log(message, level="INFO"):
    n = datetime.now()
    ns = n.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ns} " + f"[{level.upper()}".ljust(10, " ") + f"] {message}")


async def get_storeglide_page(session: ClientSession, page=1):
    output_log(f"Getting storeglide page {page}")
    url = STOREGLIDE_URL + f"?page={page}"
    async with session.get(url) as resp:
        result = await resp.text()
    return result


async def get_storeglide_pages_deep(session: ClientSession) -> List[str]:
    output_log("Getting storeglide pages")
    tasks = []
    for i in range(1, STOREGLIDE_PAGES_DEEP + 1):
        tasks.append(asyncio.create_task(
            get_storeglide_page(session, i)
        ))
    results = await asyncio.gather(*tasks)
    output_log("Pages download done")

    return results


def parse_page_for_apps(page: str) -> AppList:
    output_log("Starting page parsing")
    soup = BeautifulSoup(page, 'html.parser')
    apps = soup.find_all('li', {'class': 'app'})
    parsed_apps = []
    for app in apps:
        name = app.find('span', {'class': 'name'}).text
        author = app.find('span', {'class': 'author'}).text.replace('by ', '')
        countries = app.find('span', {'class': 'countries'}).text.strip()
        link = app.find('a', {'class': 'download'}).get('href')
        app_info = {
            'name': name,
            'author': author,
            'countries': countries,
            'link': link
        }
        parsed_apps.append(app_info)
    if not apps:
        output_log("No apps found after parsing", "ERROR")
    output_log("Parsing done")
    return parsed_apps


def parse_pages(page_list: List[str]) -> AppList:
    output_log("Starting pages parsing")
    parsed_apps = list()
    for page in page_list:
        parsed_apps += parse_page_for_apps(page)
    output_log("All pages parsing done")

    return parsed_apps


async def insert_apps(apps: AppList):
    output_log("Inserting apps")
    tasks = [
        asyncio.create_task(db.create_app(app)) for app in apps
    ]

    results = await asyncio.gather(*tasks)
    output_log(f"Insert results: {results}")
    return results


async def start_spider():
    output_log("Starting cycle")
    while True:
        connector = ProxyConnector.from_url(PROXY_URL)
        async with ClientSession(connector=connector) as session:
            pages = await get_storeglide_pages_deep(session)

        apps = parse_pages(pages)
        await insert_apps(apps)
        output_log(f"Sleeping for {SLEEP_TIMER_SECS} seconds")
        await asyncio.sleep(SLEEP_TIMER_SECS)


async def shutdown(loop, signal=None):
    if signal:
        output_log(f"Received exit signal {signal.name}")
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    output_log(f"Cancelling {len(tasks)} tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    output_log(f"Closing database session")
    db.client.close()
    output_log("Done.")
    loop.stop()


def handle_uncaught_exception(loop, context):
    msg = context.get("exception", context["message"])
    output_log(f"Caught exception: {msg}", "ERROR")
    output_log("Shutting down")
    asyncio.create_task(shutdown(loop))


if __name__ == "__main__":
    sleep(5)
    loop = asyncio.get_event_loop()
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(loop, signal=s)))
    loop.set_exception_handler(handle_uncaught_exception)
    try:
        loop.create_task(start_spider())
        loop.run_forever()
    finally:
        output_log("Successfully shutdown Spider")
        loop.close()
