import os
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from app.models.schemas import (
    TargetConfiguration, SearchPlan, TrackResult, AttributeDetail, DetectionItem
)

# Standard Color Mapping for robust HSV comparison
COLOR_HSV_RANGES = {
    "red": [
        ((0, 70, 50), (10, 255, 255)),
        ((170, 70, 50), (180, 255, 255))
    ],
    "blue": [((100, 70, 50), (135, 255, 255))],
    "green": [((35, 50, 50), (85, 255, 255))],
    "yellow": [((20, 100, 100), (35, 255, 255))],
    "black": [((0, 0, 0), (180, 255, 60))],
    "dark": [((0, 0, 0), (180, 255, 80))],
    "white": [((0, 0, 200), (180, 30, 255))],
    "grey": [((0, 0, 60), (180, 40, 200))],
    "orange": [((11, 100, 100), (25, 255, 255))],
    "khaki": [((15, 20, 100), (35, 150, 255))],
    "beige": [((10, 10, 150), (30, 100, 255))]
}

class AppearanceAnalyzer:
    @staticmethod
    def analyze_crop_colors(crop_path_full: str) -> Dict[str, float]:
        """
        Analyzes upper-body (top 45%) and lower-body (bottom 45%) color proportions.
        """
        results = {}
        if not os.path.exists(crop_path_full):
            return results

        img = cv2.imread(crop_path_full)
        if img is None or img.size == 0:
            return results

        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Backpack region (upper-back/center)
        bp_y1, bp_y2 = int(h * 0.15), int(h * 0.6)
        bp_x1, bp_x2 = int(w * 0.2), int(w * 0.8)
        backpack_hsv = hsv[bp_y1:bp_y2, bp_x1:bp_x2]

        # Upper body region
        up_y1, up_y2 = int(h * 0.1), int(h * 0.55)
        upper_hsv = hsv[up_y1:up_y2, :]

        # Create a mask for the upper body that EXCLUDES the backpack
        upper_mask = np.ones(upper_hsv.shape[:2], dtype=np.uint8) * 255
        rel_bp_y1 = max(0, bp_y1 - up_y1)
        rel_bp_y2 = min(up_y2 - up_y1, bp_y2 - up_y1)
        if rel_bp_y1 < rel_bp_y2:
            upper_mask[rel_bp_y1:rel_bp_y2, bp_x1:bp_x2] = 0

        # Lower body region
        lower_hsv = hsv[int(h * 0.50):int(h * 0.90), :]

        # Helper to analyze a region
        def analyze_region(region_hsv, prefix, multiplier, mask_roi=None):
            if region_hsv.size == 0:
                return
            if mask_roi is not None:
                pixels = cv2.countNonZero(mask_roi)
            else:
                pixels = region_hsv.shape[0] * region_hsv.shape[1]
                
            if pixels == 0:
                return

            for color_name, ranges in COLOR_HSV_RANGES.items():
                mask = np.zeros(region_hsv.shape[:2], dtype=np.uint8)
                for lower, upper in ranges:
                    mask |= cv2.inRange(region_hsv, np.array(lower), np.array(upper))
                
                if mask_roi is not None:
                    mask = cv2.bitwise_and(mask, mask, mask=mask_roi)

                match_pct = float(np.sum(mask > 0)) / float(max(1, pixels))
                results[f"{prefix}_{color_name}"] = min(1.0, match_pct * multiplier)

        analyze_region(upper_hsv, "upper", 2.2, mask_roi=upper_mask)
        analyze_region(lower_hsv, "lower", 2.2)
        analyze_region(backpack_hsv, "backpack", 2.5)

        return results

    @staticmethod
    def get_color_score(target_text: str, region_prefix: str, color_feats: Dict[str, float]) -> float:
        if not target_text:
            return 0.5
        target_text = target_text.lower()
        best_score = 0.0
        found_color = False
        for color in COLOR_HSV_RANGES.keys():
            if color in target_text:
                found_color = True
                best_score = max(best_score, color_feats.get(f"{region_prefix}_{color}", 0.0))
        if "dark" in target_text or "black" in target_text:
            found_color = True
            best_score = max(best_score, color_feats.get(f"{region_prefix}_dark", 0.0), color_feats.get(f"{region_prefix}_black", 0.0))
        return best_score if found_color else 0.1

    @staticmethod
    def get_dominant_color(region_prefix: str, color_feats: Dict[str, float]) -> str:
        best_c = "mixed"
        best_s = 0.0
        for color in COLOR_HSV_RANGES.keys():
            s = color_feats.get(f"{region_prefix}_{color}", 0.0)
            if s > best_s:
                best_s = s
                best_c = color
        return best_c if best_s > 0.3 else "mixed/dark"

    @classmethod
    def evaluate_track(
        cls,
        session_id: str,
        track_id: int,
        detections: List[DetectionItem],
        target_config: TargetConfiguration,
        search_plan: SearchPlan,
        data_base_dir: str
    ) -> TrackResult:
        if not detections:
            raise ValueError(f"Track {track_id} has no detections.")

        # Sort detections by timestamp
        detections = sorted(detections, key=lambda d: d.timestamp_seconds)
        first_seen = detections[0].timestamp_seconds
        last_seen = detections[-1].timestamp_seconds

        # Find detection with highest crop quality
        best_det = max(detections, key=lambda d: d.quality_score * d.confidence)
        best_timestamp = best_det.timestamp_seconds

        # Aggregate crop features across detections
        analyzed_count = 0
        upper_scores = []
        lower_scores = []
        backpack_scores = []
        qualities = []
        confidences = []
        crop_samples = []
        
        color_feats = {}

        for det in detections:
            confidences.append(det.confidence)
            qualities.append(det.quality_score)
            if det.crop_path:
                crop_samples.append(det.crop_path)
                full_path = os.path.join(data_base_dir, det.crop_path.lstrip("/\\"))
                if os.path.exists(full_path):
                    analyzed_count += 1
                    color_feats = cls.analyze_crop_colors(full_path)

                    if target_config.upper_clothing_color:
                        upper_scores.append(cls.get_color_score(target_config.upper_clothing_color, "upper", color_feats))
                    else:
                        upper_scores.append(0.5)

                    if target_config.lower_clothing_color:
                        lower_scores.append(cls.get_color_score(target_config.lower_clothing_color, "lower", color_feats))
                    else:
                        lower_scores.append(0.5)

                    if target_config.backpack:
                        backpack_scores.append(cls.get_color_score(target_config.backpack, "backpack", color_feats))

        avg_det_conf = float(np.mean(confidences)) if confidences else 0.5
        avg_quality = float(np.mean(qualities)) if qualities else 0.5

        avg_upper = float(np.mean(upper_scores)) if upper_scores else 0.4
        avg_lower = float(np.mean(lower_scores)) if lower_scores else 0.4
        avg_backpack = float(np.mean(backpack_scores)) if backpack_scores else 0.3

        # Compute appearance similarity
        weights = []
        vals = []
        if target_config.upper_clothing_color:
            weights.append(0.40)
            vals.append(avg_upper)
        if target_config.lower_clothing_color:
            weights.append(0.30)
            vals.append(avg_lower)
        if target_config.backpack and target_config.backpack.lower() not in ["none", ""]:
            weights.append(0.30)
            vals.append(avg_backpack)

        if sum(weights) > 0:
            appearance_similarity = float(sum(w * v for w, v in zip(weights, vals)) / sum(weights))
        else:
            appearance_similarity = 0.50

        # Temporal consistency across observations
        consistency = min(1.0, len(detections) / 5.0)

        # Evidence quality score
        evidence_quality = round(0.5 * avg_quality + 0.5 * consistency, 2)

        # Final ranking score formula
        final_ranking_score = round(
            0.70 * appearance_similarity +
            0.15 * avg_det_conf +
            0.10 * evidence_quality +
            0.05 * (1.0 if analyzed_count >= 2 else 0.5),
            2
        )

        # Build detailed attribute breakdown
        attributes: Dict[str, AttributeDetail] = {}

        # Upper clothing attribute
        exp_upper = f"{target_config.upper_clothing_color or ''} {target_config.upper_clothing_type or ''}".strip()
        obs_upper_color = cls.get_dominant_color("upper", color_feats) if color_feats else "unknown"
        attributes["upper_clothing"] = AttributeDetail(
            expected=exp_upper or "Target upper clothing",
            observed=f"{obs_upper_color} upper clothing",
            score=round(avg_upper, 2),
            visibility="clear" if avg_quality > 0.5 else "partial"
        )

        # Lower clothing attribute
        exp_lower = f"{target_config.lower_clothing_color or ''} {target_config.lower_clothing_type or ''}".strip()
        obs_lower_color = cls.get_dominant_color("lower", color_feats) if color_feats else "unknown"
        attributes["lower_clothing"] = AttributeDetail(
            expected=exp_lower or "Target lower clothing",
            observed=f"{obs_lower_color} lower clothing",
            score=round(avg_lower, 2),
            visibility="clear" if avg_quality > 0.5 else "partial"
        )

        # Backpack attribute
        if target_config.backpack:
            obs_bp_color = cls.get_dominant_color("backpack", color_feats) if color_feats else "unknown"
            attributes["backpack"] = AttributeDetail(
                expected=target_config.backpack,
                observed=f"{obs_bp_color} backpack-like object" if avg_backpack > 0.4 else "unclear rear object",
                score=round(avg_backpack, 2),
                visibility="clear" if avg_backpack > 0.4 else "obscured"
            )

        # Hair & Shoes marked as unknown due to aerial top-down SAR angle
        attributes["hair"] = AttributeDetail(
            expected=f"{target_config.hair_length or ''} {target_config.hair_color or ''} hair".strip() or "Hair details",
            observed="unknown",
            score=None,
            visibility="not_visible"
        )
        attributes["shoes"] = AttributeDetail(
            expected=f"{target_config.shoe_color or ''} shoes".strip() or "Shoe details",
            observed="unknown",
            score=None,
            visibility="not_visible"
        )

        # Collect Evidence Lists
        matching_evidence = []
        conflicting_evidence = []
        unknown_attributes = ["Hair color/length", "Shoe details"]

        if avg_upper >= 0.65:
            matching_evidence.append(f"Prominent {attributes['upper_clothing'].observed} matching target")
        elif avg_upper < 0.35:
            conflicting_evidence.append(f"Upper clothing color conflict: observed {attributes['upper_clothing'].observed}")

        if avg_lower >= 0.55:
            matching_evidence.append(f"Matching {attributes['lower_clothing'].observed}")

        if target_config.backpack and avg_backpack >= 0.45:
            matching_evidence.append(f"Distinct {attributes['backpack'].observed} visible across multiple frames")

        # Track classification decision
        if final_ranking_score >= 0.78 and not conflicting_evidence:
            classification = "strong_match"
            requires_review = False
            explanation = f"Strong appearance match with {len(matching_evidence)} matching attributes across {len(detections)} frames."
        elif final_ranking_score >= 0.55:
            classification = "possible_match"
            requires_review = True
            explanation = f"Possible appearance match at {int(best_timestamp//60):02d}:{int(best_timestamp%60):02d}. Human confirmation required."
        elif evidence_quality < 0.30:
            classification = "insufficient_visibility"
            requires_review = True
            explanation = "Subject detected but motion blur or small crop size prevents conclusive attribute matching."
        else:
            classification = "unlikely_match"
            requires_review = False
            explanation = "Low similarity score or conflicting clothing features detected."

        best_frame_path = best_det.crop_path or (crop_samples[0] if crop_samples else "")

        return TrackResult(
            session_id=session_id,
            track_id=track_id,
            first_seen_seconds=round(first_seen, 2),
            last_seen_seconds=round(last_seen, 2),
            best_timestamp_seconds=round(best_timestamp, 2),
            classification=classification,
            person_detection_confidence=round(avg_det_conf, 2),
            appearance_similarity=round(appearance_similarity, 2),
            evidence_quality=evidence_quality,
            final_ranking_score=final_ranking_score,
            observations_analyzed=len(detections),
            attributes=attributes,
            matching_evidence=matching_evidence,
            conflicting_evidence=conflicting_evidence,
            unknown_attributes=unknown_attributes,
            requires_human_review=requires_review,
            explanation=explanation,
            best_frame_path=best_frame_path,
            cropped_samples=crop_samples[:6],
            human_feedback=None,
            human_notes=None,
            gps_location=None
        )
