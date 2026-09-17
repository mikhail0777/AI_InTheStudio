"""Conservative structured parser used before model-backed query reasoning is added."""
import re
from typing import Dict, List, Tuple

from app.models.open_vocabulary import (
    ActionConstraint, AttributeConstraint, EntityMention, ModelProvenance,
    RelationshipConstraint, SearchQuery,
)


COLORS = ("yellow", "red", "blue", "green", "black", "white", "gray", "grey", "brown", "orange", "purple", "pink")
ENTITY_ALIASES: Dict[str, Tuple[str, str]] = {
    "woman": ("person", "woman"), "man": ("person", "man"), "person": ("person", "person"),
    "child": ("person", "child"), "someone": ("person", "person"),
    "tesla": ("car", "Tesla"), "car": ("car", "car"), "vehicle": ("vehicle", "vehicle"),
    "truck": ("truck", "truck"), "bicycle": ("bicycle", "bicycle"), "bike": ("bicycle", "bicycle"),
    "dog": ("dog", "dog"), "stroller": ("stroller", "stroller"),
    "backpack": ("backpack", "backpack"), "package": ("package", "package"),
    "door": ("door", "door"), "building": ("building", "building"), "helmet": ("helmet", "helmet"),
}
ACTIONS = {"pushing": "pushing", "pushes": "pushing", "running": "running", "carrying": "carrying",
           "entering": "entering", "enters": "entering", "falling": "falling", "placing": "placing",
           "leaving": "leaving", "opens": "opening", "picking": "picking_up"}
RELATIONSHIPS = {"beside": "beside", "near": "near", "behind": "behind", "inside": "inside"}


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class StructuredQueryParser:
    @property
    def provenance(self):
        return ModelProvenance(
            provider="local-deterministic", model_name="conservative-query-parser",
            model_version="1", device="cpu",
        )

    def parse(self, text: str, processing_mode: str = "balanced") -> SearchQuery:
        original = text.strip()
        if not original:
            raise ValueError("Describe what to find in the video.")
        words = _tokens(original)
        entities = []
        positions = []
        counts: Dict[str, int] = {}
        for position, word in enumerate(words):
            if word not in ENTITY_ALIASES:
                continue
            entity_type, name = ENTITY_ALIASES[word]
            base_id = entity_type
            counts[base_id] = counts.get(base_id, 0) + 1
            entity_id = base_id if counts[base_id] == 1 else f"{base_id}_{counts[base_id]}"
            negative = position > 0 and words[position - 1] in ("without", "no")
            attributes = []
            for color_position, color in enumerate(words):
                if color in COLORS and 0 < position - color_position <= 2:
                    normalized = "gray" if color == "grey" else color
                    attributes.append(AttributeConstraint(
                        criterion_id=f"{entity_id}.color", entity_id=entity_id,
                        name="color", value=normalized, required=True, negative=False,
                    ))
                    break
            entities.append(EntityMention(
                entity_id=entity_id, name=name, entity_type=entity_type,
                required=True, negative=negative, attributes=attributes,
            ))
            positions.append(position)
        required = []
        for entity in entities:
            required.append(entity.entity_id)
            required.extend(attribute.criterion_id for attribute in entity.attributes if attribute.required)
        actions = []
        relationships = []
        for position, word in enumerate(words):
            if word in ACTIONS and entities:
                before = [item for item in zip(positions, entities) if item[0] < position]
                after = [item for item in zip(positions, entities) if item[0] > position]
                actor = (before[-1][1] if before else entities[0]).entity_id
                obj = after[0][1].entity_id if after else None
                criterion_id = f"{actor}.{ACTIONS[word]}" + (f".{obj}" if obj else "")
                actions.append(ActionConstraint(
                    criterion_id=criterion_id, actor_entity_id=actor, action=ACTIONS[word],
                    object_entity_id=obj, requires_temporal_evidence=True,
                ))
                required.append(criterion_id)
            if word in RELATIONSHIPS and len(entities) >= 2:
                before = [item for item in zip(positions, entities) if item[0] < position]
                after = [item for item in zip(positions, entities) if item[0] > position]
                if before and after:
                    subject, obj = before[-1][1].entity_id, after[0][1].entity_id
                    criterion_id = f"{subject}.{RELATIONSHIPS[word]}.{obj}"
                    relationships.append(RelationshipConstraint(
                        criterion_id=criterion_id, subject_entity_id=subject,
                        predicate=RELATIONSHIPS[word], object_entity_id=obj,
                    ))
                    required.append(criterion_id)
        unsupported = [] if entities else [original]
        return SearchQuery(
            original_text=original, entities=entities, actions=actions, relationships=relationships,
            required_evidence_ids=list(dict.fromkeys(required)), unsupported_concepts=unsupported,
            processing_mode=processing_mode, parser_provenance=self.provenance,
        )


def should_use_generic_search(query: SearchQuery) -> bool:
    """Keep legacy person-only appearance searches working until their Phase 8 migration."""
    # The first mentioned entity is the subject of the current vertical slice.
    # Secondary objects must not silently reroute established person searches.
    return bool(query.entities) and query.entities[0].entity_type != "person"
