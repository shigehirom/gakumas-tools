#!/bin/bash
json_file="/Users/shigehiro/.mongodb/mongodb-mcp/exports/6a1fa00c624199992ea69b97/6a2000db624199992ea69b99.json"
img_dir="packages/gakumas-images/images/pIdols"
out_file="owned_p_idols_obsidian.md"

echo "# 所有Pアイドル一覧（プラン・アイドル別）" > "$out_file"
echo "" >> "$out_file"
echo "このマークダウンは、所有しているPアイドルをプランごと、アイドル順に整理し、アイコン画像をBase64形式で埋め込んだものです。Obsidian等にそのまま貼り付けてご利用いただけます。" >> "$out_file"
echo "" >> "$out_file"

for plan in "sense" "logic" "anomaly"; do
  case $plan in
    "sense") plan_name="Sense (センス)" ;;
    "logic") plan_name="Logic (ロジック)" ;;
    "anomaly") plan_name="Anomaly (アノマリー)" ;;
  esac
  
  count=$(/opt/homebrew/bin/jq -r --arg plan "$plan" '[.[] | select(.plan == $plan)] | length' "$json_file")
  if [ "$count" -eq 0 ]; then
    continue
  fi
  
  echo "# $plan_name" >> "$out_file"
  echo "" >> "$out_file"
  
  /opt/homebrew/bin/jq -r --arg plan "$plan" '
    [.[] | select(.plan == $plan)] | group_by(.idolId) | sort_by(.[0].idolId) | .[] | 
    "\(.[0].idolId)\t\(.[0].idol_name)"
  ' "$json_file" | while IFS=$'\t' read -r idolId idol_name; do
    echo "## $idol_name" >> "$out_file"
    echo "" >> "$out_file"
    echo "| 画像 | Pアイドル (楽曲名) | レアリティ |" >> "$out_file"
    echo "| :---: | :--- | :---: |" >> "$out_file"
    
    /opt/homebrew/bin/jq -r --arg plan "$plan" --arg idol "$idol_name" '
      [.[] | select(.plan == $plan and .idol_name == $idol)] | 
      sort_by(if .rarity == "SSR" then 1 elif .rarity == "SR" then 2 else 3 end, .id) |
      .[] | "\(.id)\t\(.title)\t\(.rarity)"
    ' "$json_file" | while IFS=$'\t' read -r id title rarity; do
      img_path="$img_dir/${id}.png"
      if [ -f "$img_path" ]; then
        b64=$(base64 -i "$img_path")
        img="![${title}](data:image/png;base64,${b64})"
      else
        img="No Image"
      fi
      echo "| $img | **$title** | $rarity |" >> "$out_file"
    done
    echo "" >> "$out_file"
  done
done
echo "Markdown generated at $out_file"
