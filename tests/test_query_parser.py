import unittest

from app.services.query_parser import StructuredQueryParser, should_use_generic_search


class QueryParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = StructuredQueryParser()

    def test_yellow_car_is_required_generic_evidence(self):
        query = self.parser.parse("A yellow car")
        self.assertTrue(should_use_generic_search(query))
        self.assertEqual(query.entities[0].entity_type, "car")
        self.assertEqual(query.entities[0].attributes[0].value, "yellow")
        self.assertEqual(query.required_evidence_ids, ["car", "car.color"])

    def test_relationship_and_temporal_action_retain_participants(self):
        query = self.parser.parse("A woman pushing a stroller near a building")
        self.assertEqual(query.actions[0].action, "pushing")
        self.assertTrue(query.actions[0].requires_temporal_evidence)
        self.assertEqual(query.relationships[0].predicate, "near")
        self.assertIn(query.actions[0].criterion_id, query.required_evidence_ids)

    def test_unknown_query_is_not_silently_mapped_to_clothing(self):
        query = self.parser.parse("a mysterious glowing orb")
        self.assertFalse(query.entities)
        self.assertEqual(query.unsupported_concepts, ["a mysterious glowing orb"])

    def test_person_with_secondary_object_stays_on_legacy_pipeline(self):
        query = self.parser.parse("person carrying a blue backpack")
        self.assertFalse(should_use_generic_search(query))

    def test_person_stroller_interaction_uses_generic_pipeline(self):
        query = self.parser.parse("person pushing a stroller")
        self.assertTrue(should_use_generic_search(query))

    def test_quantity_and_negative_entities_are_explicit(self):
        query = self.parser.parse("two people near a car without a dog")
        self.assertEqual(query.entities[0].quantity, 2)
        self.assertTrue(query.entities[-1].negative)
        self.assertIn(query.entities[-1].entity_id, query.required_evidence_ids)

    def test_person_quantity_uses_generic_pipeline(self):
        self.assertTrue(should_use_generic_search(self.parser.parse("two people")))

    def test_negative_backpack_keeps_specialist_compatibility(self):
        self.assertFalse(should_use_generic_search(self.parser.parse("person without a backpack")))

    def test_ordered_actions_create_required_event_steps(self):
        query = self.parser.parse("a person running then carrying a package")
        self.assertEqual([step.order for step in query.event_sequence], [0, 1])
        self.assertIsNone(query.actions[0].object_entity_id)
        self.assertEqual(query.actions[1].object_entity_id, "package")
        self.assertTrue(all(step.step_id in query.required_evidence_ids for step in query.event_sequence))

    def test_repeated_ordered_action_has_unique_criteria(self):
        query = self.parser.parse("a person running then running")
        self.assertEqual(len({action.criterion_id for action in query.actions}), 2)
        self.assertEqual(len(query.event_sequence), 2)

    def test_negated_action_and_relationship_are_explicit(self):
        query = self.parser.parse("a dog not running near a bicycle")
        self.assertTrue(query.actions[0].negative)
        self.assertFalse(query.relationships[0].negative)

    def test_generic_carrying_object_is_not_routed_to_legacy(self):
        query = self.parser.parse("person carrying a package")
        self.assertTrue(should_use_generic_search(query))


if __name__ == "__main__":
    unittest.main()
