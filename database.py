import pymongo.errors
from bson import ObjectId
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from motor.core import Collection, Database
from pymongo.results import InsertOneResult, UpdateResult
from typing import Dict


USER = "mongo"
PASSWORD = "mongo"
HOST = "mongo"
PORT = "27017"

URI = f"mongodb://{USER}:{PASSWORD}@{HOST}:{PORT}"

client = AsyncIOMotorClient(URI)
db: Database = client.storglide
users_coll: Collection = db.users
apps_coll: Collection = db.apps
queue_coll: Collection = db.queue_coll


async def create_app(app: Dict[str, str]):
    app_in_db = app.copy()
    app_in_db.update({"created": datetime.now(), "notified": False})
    try:
        result = await apps_coll.insert_one(app_in_db)
        result = result.inserted_id
    except pymongo.errors.DuplicateKeyError:
        result = None

    return result


async def change_app_notification_status(app_id: ObjectId, notified: bool):
    app = {"_id": app_id}
    query = {"$set": {"notified": notified}}

    result: UpdateResult = await apps_coll.update_one(app, query)
    return result.modified_count


async def get_app(app_id: ObjectId):
    query = {"_id": app_id}
    return await apps_coll.find_one(query)


def get_not_notified_apps():
    query = {"notified": False}
    cursor = apps_coll.find(query)

    return cursor


def search_apps_by_dev(dev_string: str):
    if not dev_string.startswith('"') and not dev_string.endswith('"'):
        dev_string = '"' + dev_string + '"'

    query = {
        "$text": {"$search": dev_string}
    }
    score = {
        "score": {"$meta": "textScore"}
    }
    cursor = apps_coll.find(query, score)
    cursor.sort([('score', {"$meta": "textScore"})])

    return cursor


async def create_user(cid: int):
    query = {
        "cid": cid,
        "active": True,
        "developers": []
    }

    result: InsertOneResult = await users_coll.insert_one(query)
    return result.inserted_id


async def change_user_status(cid: int, active: bool):
    user = {"cid": cid}
    query = {"$set": {"active": active}}

    result: UpdateResult = await users_coll.update_one(user, query)
    return result.modified_count


async def get_user(cid: int):
    user = {"cid": cid}

    result = await users_coll.find_one(user)
    return result


def get_users_by_developer(dev: str):
    query = {"developers": dev}
    cursor = users_coll.find(query)

    return cursor


async def add_developer(cid: int, developer: str):
    devs = await get_developers(cid)
    if developer in devs:
        raise pymongo.errors.DuplicateKeyError(f"{developer} is already in list")
    user = {"cid": cid}
    query = {"$push": {"developers": developer}}

    result: UpdateResult = await users_coll.update_one(user, query)
    return result.modified_count


async def del_developer(cid: int, developer: str):
    user = {"cid": cid}
    query = {"$pull": {"developers": developer}}

    result: UpdateResult = await users_coll.update_one(user, query)
    return result.modified_count


async def get_developers(cid: int):
    user = {"cid": cid}
    projection = {"developers": 1}

    result = await users_coll.find_one(user, projection=projection)
    return result["developers"] if result else list()


async def get_user_last_developer(cid: int):
    user = {"cid": cid}
    slicer = {"developers": {"$slice": -1}}
    result = await users_coll.find_one(user, slicer)
    result = result["developers"] if result["developers"] else []

    return result


async def insert_task(task: Dict):
    result: InsertOneResult = await queue_coll.insert_one(task)
    return result.inserted_id


async def get_rsearch_task():
    task = await queue_coll.find_one_and_delete(
        {'type': 'rsearch'}, sort=[('_id', pymongo.ASCENDING)]
    )

    return task
