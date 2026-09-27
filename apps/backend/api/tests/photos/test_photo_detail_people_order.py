from django.test import SimpleTestCase

from api.serializers.photos import _photo_people_entry_sort_key


class PhotoDetailPeopleOrderTestCase(SimpleTestCase):
    def test_confirmed_before_inferred_before_unnamed(self):
        confirmed = {"type": "user", "name": "Zara", "probability": 1, "face_id": 3}
        inferred = {
            "type": "classification",
            "name": "Alice",
            "probability": 0.99,
            "face_id": 1,
        }
        unnamed = {"type": "", "name": "", "probability": 0, "face_id": 2}
        ordered = sorted(
            [unnamed, inferred, confirmed],
            key=_photo_people_entry_sort_key,
        )
        self.assertEqual([e["face_id"] for e in ordered], [3, 1, 2])

    def test_inferred_sorted_by_probability_then_name(self):
        low = {"type": "classification", "name": "Bob", "probability": 0.4, "face_id": 1}
        high = {"type": "classification", "name": "Alice", "probability": 0.9, "face_id": 2}
        ordered = sorted([low, high], key=_photo_people_entry_sort_key)
        self.assertEqual(ordered[0]["face_id"], 2)
