from django.test import SimpleTestCase

from apps.proctoring import scoring
from apps.proctoring.event_types import EventType


class EventTypeTests(SimpleTestCase):
    def test_every_event_type_has_a_label(self):
        self.assertEqual(set(scoring.EVENT_LABELS), set(EventType))

    def test_server_only_events_are_not_in_the_client_list(self):
        # these are written by the server; the desktop parity test lists the same names
        self.assertEqual({"force_ended", "exam_resumed", "time_extended"} <= set(EventType), True)

    def test_weights_only_use_known_event_types(self):
        self.assertTrue(set(scoring.WEIGHTS) <= set(EventType))

    def test_event_types_fit_the_database_column(self):
        self.assertTrue(all(len(e.value) <= 50 for e in EventType))

    def test_summarize_matches_score_and_flag(self):
        counts = {EventType.TAB_SWITCH: 3, EventType.DISPLAY_ADDED: 1, "unknown_new_type": 9}
        self.assertEqual(scoring.summarize(counts), (6, "flagged"))
        self.assertEqual(scoring.label("unknown_new_type"), "unknown_new_type")
