import json
import os
import glob

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SUPPORT_DIR = os.path.join(os.path.dirname(TOOLS_DIR), "gakumas-support_cards", "support_cards")

# Load maps
with open(os.path.join(TOOLS_DIR, "packages", "gakumas-data", "json", "skill_cards.json"), 'r', encoding='utf-8') as f:
    skill_cards = json.load(f)
with open(os.path.join(TOOLS_DIR, "packages", "gakumas-data", "json", "p_items.json"), 'r', encoding='utf-8') as f:
    p_items = json.load(f)

sc_map = {c["name"]: c["id"] for c in skill_cards if not c.get("upgraded")}
pi_map = {c["name"]: c["id"] for c in p_items if not c.get("upgraded")}

updated_count = 0
for filepath in glob.glob(os.path.join(SUPPORT_DIR, "*.json")):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    changed = False
    for item in data:
        # Check obtained_skill_card
        if item.get("obtained_skill_card"):
            name = item["obtained_skill_card"]
            if name in sc_map and item.get("obtained_skill_card_id") != sc_map[name]:
                # Insert the ID directly after obtained_skill_card for readability, 
                # but dict order is preserved in Python 3.7+ anyway.
                item["obtained_skill_card_id"] = sc_map[name]
                changed = True
                
        # Check obtained_item
        if item.get("obtained_item"):
            name = item["obtained_item"]
            if name in pi_map and item.get("obtained_item_id") != pi_map[name]:
                item["obtained_item_id"] = pi_map[name]
                changed = True
    
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Updated {os.path.basename(filepath)}")
        updated_count += 1

print(f"Update complete. {updated_count} files were modified.")
