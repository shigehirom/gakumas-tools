import SKILL_CARD_ICON_KEYS from "./images/skillCards/icons/keys.json" with { type: "json" };

const GK_IMG_BASE_URL = process.env.NEXT_PUBLIC_GK_IMG_BASE_URL || "";

const SKILL_CARD_ICON_KEY_SET = new Set(SKILL_CARD_ICON_KEYS);

export default function getImages(entity, idolId = 6) {
  switch (entity?._type) {
    case "idol":
      return { icon: `${GK_IMG_BASE_URL}/idols/${entity.id}.png` };
    case "pDrink":
      return {
        icon: `${GK_IMG_BASE_URL}/p_drinks/icons/${entity.id}.webp`,
        details: `${GK_IMG_BASE_URL}/p_drinks/details/${entity.id}.webp`,
      };
    case "pIdol":
      return { icon: `/images/p_idols/${entity.id}.png` };
    case "pItem":
      return {
        icon: `${GK_IMG_BASE_URL}/p_items/icons/${entity.id}.webp`,
        details: `${GK_IMG_BASE_URL}/p_items/details/${entity.id}.webp`,
      };
    case "skillCard": {
      let fileName = `${entity.id}`;
      if (SKILL_CARD_ICON_KEY_SET.has(`${entity.id}_${idolId}`)) {
        fileName = `${entity.id}_${idolId}`;
      } else if (SKILL_CARD_ICON_KEY_SET.has(`${entity.id}_6`)) {
        fileName = `${entity.id}_6`;
      }
      return {
        icon: `${GK_IMG_BASE_URL}/skill_cards/icons/${fileName}.webp`,
        details: `${GK_IMG_BASE_URL}/skill_cards/details/${entity.id}.webp`,
      };
    }
    default:
      return {};
  }
}

export function isGkImgUrl(src) {
  return (
    typeof src == "string" &&
    ((!!GK_IMG_BASE_URL && src.startsWith(GK_IMG_BASE_URL)) ||
      src.startsWith("/images/p_idols/"))
  );
}
