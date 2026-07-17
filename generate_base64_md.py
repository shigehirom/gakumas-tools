import pymongo
import base64
import os
import json

uri = "mongodb://192.168.100.4:27017"
client = pymongo.MongoClient(uri)
db = client["gakumas-tools"]
coll = db["owned_p_idols"]

idols = list(coll.find({}))

plans = {"sense": {}, "logic": {}, "anomaly": {}}
planNames = {"sense": "Sense (センス)", "logic": "Logic (ロジック)", "anomaly": "Anomaly (アノマリー)"}
rarityOrder = {"SSR": 1, "SR": 2, "R": 3}
idolOrder = {
    "花海 咲季": 1, "月村 手毬": 2, "藤田 ことね": 3, "有村 麻央": 4,
    "葛城 リーリヤ": 5, "倉本 千奈": 6, "紫雲 清夏": 7, "篠澤 広": 8,
    "姫崎 莉波": 9, "花海 佑芽": 10, "十王 星南": 11, "秦谷 美鈴": 12, "雨夜 燕": 13
}

for idol in idols:
    plan = idol.get("plan", "unknown")
    if plan not in plans:
        plans[plan] = {}
    
    idolId = idol.get("idolId", 999)
    if idolId not in plans[plan]:
        plans[plan][idolId] = {"idol_name": idol.get("idol_name"), "cards": []}
    
    plans[plan][idolId]["cards"].append(idol)

md = "# 所有Pアイドル一覧（プラン・アイドル別）\n\n"
md += "このマークダウンは、所有しているPアイドルをプランごと、アイドル順に整理し、アイコン画像をBase64形式で埋め込んだものです。Obsidian等にそのまま貼り付けてご利用いただけます。\n\n"

imageSrcDir = "/Users/shigehiro/gakumas-workspace/gakumas-tools/packages/gakumas-images/images/pIdols"

for planKey in ["sense", "logic", "anomaly"]:
    if planKey not in plans or not plans[planKey]:
        continue
    md += f"# {planNames[planKey]}\n\n"
    
    sorted_idolIds = sorted(plans[planKey].keys(), key=lambda k: (idolOrder.get(plans[planKey][k]["idol_name"], 999), k))
    
    for idolId in sorted_idolIds:
        group = plans[planKey][idolId]
        md += f"## {group['idol_name']}\n\n"
        md += "| 画像 | Pアイドル (楽曲名) | レアリティ |\n"
        md += "| :---: | :--- | :---: |\n"
        
        sorted_cards = sorted(group["cards"], key=lambda c: (rarityOrder.get(c.get("rarity"), 9), c.get("id", 0)))
        
        for card in sorted_cards:
            card_id = card.get("id")
            srcImage = os.path.join(imageSrcDir, f"{card_id}.png")
            imgCol = "No Image"
            if os.path.exists(srcImage):
                with open(srcImage, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    imgCol = f"![{card.get('title')}](data:image/png;base64,{encoded_string})"
            md += f"| {imgCol} | **{card.get('title')}** | {card.get('rarity')} |\n"
        md += "\n"

output_path = "/Users/shigehiro/gakumas-workspace/gakumas-tools/owned_p_idols_obsidian.md"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(md)

print(f"Markdown created at {output_path}")
