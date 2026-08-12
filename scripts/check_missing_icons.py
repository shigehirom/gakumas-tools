import os
import json

gk_img_dir = "/root/gakumas-workspace/gk-img/docs/p_idols"
gk_files = set(os.listdir(gk_img_dir)) if os.path.exists(gk_img_dir) else set()

pkg_img_dir = "/root/gakumas-workspace/gakumas-tools/packages/gakumas-images/images/pIdols"
pkg_files = set(os.listdir(pkg_img_dir)) if os.path.exists(pkg_img_dir) else set()

# Parse p_idols.csv
p_idols_csv = "/root/gakumas-workspace/gakumas-tools/packages/gakumas-data/csv/p_idols.csv"
all_p_idols = {}
with open(p_idols_csv, "r", encoding="utf-8") as f:
    lines = f.readlines()[1:] # skip header
    for line in lines:
        parts = line.strip().split(",")
        if len(parts) >= 6:
            p_id = int(parts[0])
            idol_id = int(parts[1])
            title = parts[2]
            rarity = parts[3]
            plan = parts[4]
            all_p_idols[p_id] = {
                "id": p_id,
                "idol_id": idol_id,
                "title": title,
                "rarity": rarity,
                "plan": plan
            }

# Read owned_p_idols from step output or DB
# (We already have the json list from MongoDB)
with open("/root/.gemini/antigravity-ide/brain/fde3d88f-9b30-422c-8e17-63c49902f8c2/.system_generated/steps/550/output.txt", "r") as f:
    text = f.read()
    start = text.find("[{")
    end = text.rfind("}]") + 2
    owned_1 = json.loads(text[start:end])

# Also load high IDs
with open("/root/.gemini/antigravity-ide/brain/fde3d88f-9b30-422c-8e17-63c49902f8c2/.system_generated/steps/553/output.txt", "r") as f:
    text = f.read()
    start = text.find("[{")
    end = text.rfind("}]") + 2
    owned_2 = json.loads(text[start:end])

owned_map = {}
for item in owned_1 + owned_2:
    owned_map[item["id"]] = item

print(f"Total owned P-idols: {len(owned_map)}")

# Idol names map
idol_names = {
    1: "花海 咲季", 2: "月村 手毬", 3: "藤田 ことね", 4: "有村 麻央",
    5: "葛城 リーリヤ", 6: "倉本 千奈", 7: "紫雲 清夏", 8: "篠澤 広",
    9: "姫崎 莉波", 10: "花海 佑芽", 11: "十王 星南", 12: "秦谷 美鈴",
    13: "雨夜 燕"
}

missing_in_gk_img_and_owned = []
for p_id, owned_info in sorted(owned_map.items()):
    webp_name = f"{p_id}.webp"
    png_name = f"{p_id}.png"
    in_gk = webp_name in gk_files
    in_pkg = png_name in pkg_files
    
    # Check if not in gk-img upstream (or if 147 was just added by us)
    if not in_gk or p_id == 147:
        meta = all_p_idols.get(p_id, {})
        name = owned_info.get("idol_name", idol_names.get(meta.get("idol_id", 0), "不明"))
        title = owned_info.get("title", meta.get("title", ""))
        rarity = owned_info.get("rarity", meta.get("rarity", ""))
        missing_in_gk_img_and_owned.append({
            "id": p_id,
            "idol": name,
            "title": title,
            "rarity": rarity,
            "in_gk_img": in_gk,
            "in_packages_images": in_pkg
        })

print("\n--- Missing in gk-img (Owned by User) ---")
for m in missing_in_gk_img_and_owned:
    print(f"ID: {m['id']:3d} | [{m['rarity']}] {m['idol']} 【{m['title']}】 | gk-img: {m['in_gk_img']} | packages: {m['in_packages_images']}")
