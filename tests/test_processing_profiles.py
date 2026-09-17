import unittest

from app.models.schemas import TargetConfiguration
from app.services.processing_profiles import get_processing_profile
from app.services.query_parser import StructuredQueryParser
from app.services.search_agent import SearchPlanAgent


class ProcessingProfileTests(unittest.TestCase):
    def test_modes_increase_bounded_workload(self):
        fast = get_processing_profile("fast")
        balanced = get_processing_profile("balanced")
        thorough = get_processing_profile("thorough")
        self.assertLess(fast.retrieval_limit, balanced.retrieval_limit)
        self.assertLess(balanced.retrieval_limit, thorough.retrieval_limit)
        self.assertLess(fast.localization_frame_limit, balanced.localization_frame_limit)
        self.assertLess(balanced.localization_frame_limit, thorough.localization_frame_limit)
        self.assertLessEqual(thorough.retrieval_limit, 1000)
        self.assertLessEqual(thorough.localization_frame_limit, thorough.retrieval_limit)

    def test_selected_mode_reaches_structured_query(self):
        target = TargetConfiguration(free_text_description="a yellow car", processing_mode="fast")
        query = StructuredQueryParser().parse(target.free_text_description, target.processing_mode)
        self.assertEqual(query.processing_mode, "fast")

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported processing mode"):
            get_processing_profile("unbounded")

    def test_specialist_person_scan_respects_mode(self):
        fast = SearchPlanAgent.create_search_plan(TargetConfiguration(processing_mode="fast"))
        thorough = SearchPlanAgent.create_search_plan(TargetConfiguration(processing_mode="thorough"))
        self.assertLess(fast.analysis_strategy.broad_scan_fps, thorough.analysis_strategy.broad_scan_fps)
        self.assertLess(fast.analysis_strategy.focused_scan_fps, thorough.analysis_strategy.focused_scan_fps)


if __name__ == "__main__":
    unittest.main()
