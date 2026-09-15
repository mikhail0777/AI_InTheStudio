"""Explicit description normalization; no implied general language understanding."""
import re
from app.models.schemas import TargetConfiguration, SearchPlan, AnalysisStrategy

COLORS = r"black|dark|white|gr[ae]y|green|blue|red|yellow|orange|pink|purple|brown|beige|khaki"
UPPER = r"upper clothing|long[ -]sleeve(?:d)?(?:\s+top)?|short[ -]sleeve(?:d)?(?:\s+top)?|hoodie|shirt|jacket|coat|sweater|top"
LOWER = r"lower clothing|bottoms|pants|trousers|shorts|jeans|skirt"


class SearchPlanAgent:
    @staticmethod
    def normalize_target(config: TargetConfiguration) -> TargetConfiguration:
        values = config.model_dump()
        text = config.free_text_description.lower()
        for field, names in (("upper_clothing_color", UPPER), ("lower_clothing_color", LOWER)):
            found = re.search(rf"\b({COLORS})\s+(?:{names})\b", text)
            negated = found and re.search(r'\b(?:no|not|without)\s+(?:a\s+)?$', text[:found.start()])
            if not values[field] and found and not negated:
                values[field] = found.group(1).replace("gray", "grey")
        if not values['backpack']:
            absent = re.search(rf'\b(?:no|without)\s+(?:a\s+)?(?:({COLORS})\s+)?back\s*pack\b', text)
            found = re.search(rf"\b({COLORS})\s+back\s*pack\b", text)
            if absent:
                values['backpack'] = 'no backpack' if not absent.group(1) else 'not ' + absent.group(1) + ' backpack'
            elif found:
                values['backpack'] = found.group(1) + ' backpack'
            elif re.search(r"\b(?:with|wearing|carrying|a)\s+(?:a\s+)?back\s*pack\b", text) and not re.search(r"\b(?:no|without)\s+(?:a\s+)?back\s*pack\b", text):
                values['backpack'] = 'backpack'
        return TargetConfiguration(**values)

    @staticmethod
    def create_search_plan(config: TargetConfiguration) -> SearchPlan:
        config = SearchPlanAgent.normalize_target(config)
        supported = []
        if config.upper_clothing_color:
            supported.append(f'{config.upper_clothing_color} upper clothing')
        if config.lower_clothing_color:
            supported.append(f'{config.lower_clothing_color} lower clothing')
        if config.backpack:
            supported.append(config.backpack)
        unverified = []
        for label, value in (("Clothing type", config.upper_clothing_type), ("Lower clothing type", config.lower_clothing_type), ("Hair color", config.hair_color), ("Hair length", config.hair_length), ("Shoes", config.shoe_color), ("Body build", config.body_build), ("Hat", config.hat), ("Accessories", config.other_accessories), ("Distinctive features", config.distinctive_features)):
            if value:
                unverified.append(f'{label}: {value} (not evaluated)')
        if config.free_text_description:
            unverified.append('Description is an operator note; only extracted clothing colors and backpack attributes are evaluated.')
        return SearchPlan(target_summary='; '.join(supported) or 'Review visible people; no supported appearance filters supplied.',
            high_value_attributes=supported, supporting_attributes=list(config.optional_attributes),
            low_reliability_attributes=unverified, negative_attributes=list(config.negative_attributes),
            analysis_strategy=AnalysisStrategy(broad_scan_fps=1, focused_scan_fps=3, focused_window_seconds=4,
                minimum_person_confidence=.40, minimum_alert_score=config.min_alert_confidence, minimum_track_observations=2))
