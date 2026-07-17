import PreviewPItems from "./PreviewPItems.js";
import PreviewSkillCardGroup from "./PreviewSkillCardGroup.js";
import styles from "./Preview.styles.js";

export default function Preview({
  itemIds,
  skillCardIdGroups,
  customizationGroups,
  idolId,
  isEmpty,
  imageMap,
}) {
  return (
    <div style={styles.preview}>
      <PreviewPItems itemIds={itemIds} imageMap={imageMap} />
      {skillCardIdGroups.slice(0, 4).map((cards, groupIndex) => (
        <PreviewSkillCardGroup
          key={groupIndex}
          cards={cards}
          customizationGroup={customizationGroups?.[groupIndex]}
          idolId={idolId}
          isEmpty={isEmpty}
          imageMap={imageMap}
        />
      ))}
    </div>
  );
}
