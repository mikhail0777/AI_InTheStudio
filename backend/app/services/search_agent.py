from typing import List
from app.models.schemas import TargetConfiguration, SearchPlan, AnalysisStrategy

class SearchPlanAgent:
    @staticmethod
    def create_search_plan(config: TargetConfiguration) -> SearchPlan:
        high_value = []
        supporting = []
        low_reliability = []
        negative = list(config.negative_attributes or [])

        # Upper clothing
        upper_desc = []
        if config.upper_clothing_color:
            upper_desc.append(config.upper_clothing_color)
        if config.upper_clothing_type:
            upper_desc.append(config.upper_clothing_type)
        if upper_desc:
            high_value.append(f"{' '.join(upper_desc)} upper clothing")

        # Backpack
        if config.backpack:
            high_value.append(f"{config.backpack}")

        # Lower clothing
        lower_desc = []
        if config.lower_clothing_color:
            lower_desc.append(config.lower_clothing_color)
        if config.lower_clothing_type:
            lower_desc.append(config.lower_clothing_type)
        if lower_desc:
            supporting.append(f"{' '.join(lower_desc)} lower clothing")

        # Hat / Headwear
        if config.hat:
            supporting.append(f"hat: {config.hat}")

        # Body build
        if config.body_build:
            supporting.append(f"{config.body_build} build")

        # Shoes (often low reliability from top-down overhead perspective)
        if config.shoe_color:
            low_reliability.append(f"{config.shoe_color} shoes")

        # Hair color/length (low reliability from high altitude/angle)
        hair_desc = []
        if config.hair_length:
            hair_desc.append(config.hair_length)
        if config.hair_color:
            hair_desc.append(config.hair_color)
        if hair_desc:
            low_reliability.append(f"{' '.join(hair_desc)} hair")

        # Additional required attributes to high value
        for req in config.required_attributes:
            if req not in high_value:
                high_value.append(req)

        # Additional optional attributes
        for opt in config.optional_attributes:
            if opt not in supporting and opt not in high_value:
                supporting.append(opt)

        summary_parts = []
        if high_value:
            summary_parts.append(", ".join(high_value))
        if supporting:
            summary_parts.append(", ".join(supporting))
        target_summary = f"Person with {', '.join(summary_parts)}" if summary_parts else config.free_text_description

        strategy = AnalysisStrategy(
            broad_scan_fps=1.0,
            focused_scan_fps=3.0,
            focused_window_seconds=4.0,
            minimum_person_confidence=0.40,
            minimum_alert_score=config.min_alert_confidence or 0.65,
            minimum_track_observations=2
        )

        return SearchPlan(
            target_summary=target_summary,
            high_value_attributes=high_value,
            supporting_attributes=supporting,
            low_reliability_attributes=low_reliability,
            negative_attributes=negative,
            analysis_strategy=strategy
        )
