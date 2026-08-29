import json
import glob
import os

def main():
    target_dir = "support_cards"
    json_files = glob.glob(os.path.join(target_dir, "*.json"))
    
    if not json_files:
        print(f"No JSON files found in '{target_dir}'.")
        return
        
    print(f"Checking {len(json_files)} JSON files...")
    
    missing_both = []
    
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if isinstance(data, list) and len(data) > 0:
                card_data = data[0]
            else:
                card_data = data
                
            skill_card = card_data.get('obtained_skill_card')
            item = card_data.get('obtained_item')
            
            if skill_card is None and item is None:
                missing_both.append(card_data)
                
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            
    if missing_both:
        print("\n=== Found cards with BOTH obtained_skill_card and obtained_item as null ===")
        for idx, card in enumerate(missing_both, 1):
            print(f"{idx}. {card.get('card_name', 'Unknown')} ({card.get('url', '')})")
    else:
        print("\nGreat! All cards have either an obtained_skill_card or an obtained_item.")

if __name__ == "__main__":
    main()
