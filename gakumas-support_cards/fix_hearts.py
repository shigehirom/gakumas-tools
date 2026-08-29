import os
from pymongo import MongoClient

MONGO_URL = "mongodb://192.168.100.4:27017"
client = MongoClient(MONGO_URL)
collection = client['gakumas-tools']['owned_support_cards']

# "ガールズ&#9825;トーク" -> "SP_SR_0043"
doc1 = collection.find_one({"_id": "ガールズ&#9825;トーク"})
if doc1:
    new_doc = doc1.copy()
    new_doc['_id'] = "SP_SR_0043"
    new_doc['wiki_id'] = "SP_SR_0043"
    new_doc['image_url'] = "https://image01.seesaawiki.jp/g/u/gakumasu/e8ed23ea10ea582c-s.png"
    collection.insert_one(new_doc)
    collection.delete_one({"_id": "ガールズ&#9825;トーク"})
    print("Fixed ガールズ♡トーク")

# "バレンタイン&#9825;会議中ーっ！" -> "SP_SSR_0047"
doc2 = collection.find_one({"_id": "バレンタイン&#9825;会議中ーっ！"})
if doc2:
    new_doc = doc2.copy()
    new_doc['_id'] = "SP_SSR_0047"
    new_doc['wiki_id'] = "SP_SSR_0047"
    new_doc['image_url'] = "https://image02.seesaawiki.jp/g/u/gakumasu/7c79adfa83e1c884-s.PNG"
    collection.insert_one(new_doc)
    collection.delete_one({"_id": "バレンタイン&#9825;会議中ーっ！"})
    print("Fixed バレンタイン♡会議中ーっ！")
