"""Explicit description normalization; no implied general language understanding."""
import re
from app.models.schemas import TargetConfiguration, SearchPlan, AnalysisStrategy

COLORS = r"dark\s+blue|light\s+blue|black|dark|white|gr[ae]y|green|blue|red|yellow|orange|pink|purple|brown|beige|khaki"
UPPER = r"upper clothing|button[ -]up(?:\s+shirt)?|t[ -]?shirt|long[ -]sleeve(?:d)?(?:\s+top)?|short[ -]sleeve(?:d)?(?:\s+top)?|hoodie|shirt|jacket|coat|sweater|vest|top"
LOWER = r"lower clothing|bottoms|pants|trousers|shorts|jeans|skirt"


class SearchPlanAgent:
    @staticmethod
    def normalize_target(config: TargetConfiguration) -> TargetConfiguration:
        values = config.model_dump()
        text = config.free_text_description.lower()
        upper_type = re.search(r'\b(button[ -]up(?:\s+shirt)?|t[ -]?shirt|hoodie|sweater|jacket|coat|vest|shirt|top)\b', text)
        lower_type = re.search(r'\b(shorts|pants|trousers|jeans|skirt|bottoms)\b', text)
        sleeves = re.search(r'\b(long|short)[ -]sleeve(?:d)?\b|\bsleeveless\b', text)
        if not values['upper_clothing_type'] and upper_type:
            values['upper_clothing_type'] = upper_type.group(1).replace(' ', '-').replace('button-up-shirt', 'button-up')
        if not values['lower_clothing_type'] and lower_type:
            values['lower_clothing_type'] = lower_type.group(1)
        if not values['sleeve_length'] and sleeves:
            values['sleeve_length'] = 'sleeveless' if sleeves.group(0) == 'sleeveless' else sleeves.group(1)
        for field, names in (("upper_clothing_color", UPPER), ("lower_clothing_color", LOWER)):
            found = re.search(rf"\b({COLORS})\s+(?:(?:long|short)[ -]sleeve(?:d)?\s+)?(?:{names})\b", text)
            negated = found and re.search(r'\b(?:no|not|without)\s+(?:a\s+)?$', text[:found.start()])
            if not values[field] and found and not negated:
                values[field] = re.sub(r'\s+', ' ', found.group(1).replace("gray", "grey"))
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
        mode_strategy = {
            "fast": (0.5, 2.0, 3.0),
            "balanced": (1.0, 3.0, 4.0),
            "thorough": (2.0, 5.0, 6.0),
        }[config.processing_mode]
        supported = []
        if config.upper_clothing_color:
            supported.append(f'{config.upper_clothing_color} upper clothing')
        if config.lower_clothing_color:
            supported.append(f'{config.lower_clothing_color} lower clothing')
        if config.backpack:
            supported.append(config.backpack)
        unverified = []
        for label, value in (("Clothing type", config.upper_clothing_type), ("Sleeve length", config.sleeve_length), ("Lower clothing type", config.lower_clothing_type), ("Hair color", config.hair_color), ("Hair length", config.hair_length), ("Shoes", config.shoe_color), ("Body build", config.body_build), ("Hat", config.hat), ("Eyewear", config.eyewear), ("Footwear type", config.footwear_type), ("Posture", config.posture), ("Accessories", config.other_accessories), ("Distinctive features", config.distinctive_features)):
            if value:
                unverified.append(f'{label}: {value} (not evaluated)')
        if config.free_text_description:
            unverified.append('Description is an operator note; only extracted clothing colors and backpack attributes are evaluated.')
        return SearchPlan(target_summary='; '.join(supported) or 'Review visible people; no supported appearance filters supplied.',
            high_value_attributes=supported, supporting_attributes=list(config.optional_attributes),
            low_reliability_attributes=unverified, negative_attributes=list(config.negative_attributes),
            analysis_strategy=AnalysisStrategy(broad_scan_fps=mode_strategy[0], focused_scan_fps=mode_strategy[1],
                focused_window_seconds=mode_strategy[2],
                minimum_person_confidence=.40, minimum_alert_score=config.min_alert_confidence, minimum_track_observations=2))
