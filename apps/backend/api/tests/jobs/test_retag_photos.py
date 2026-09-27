from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.tests.utils import create_test_photo, create_test_user


@override_settings(FEATURE_SCENE_CLASSIFICATION=True)
class RetagPhotosApiTest(TestCase):
    def setUp(self):
        self.user = create_test_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_tagging_stats_reports_model_keys(self):
        create_test_photo(
            owner=self.user,
            captions_json={"siglip2": {"tags": ["dog"]}, "im2txt": "a cat"},
        )
        create_test_photo(owner=self.user, captions_json={"places365": {"categories": ["beach"]}})

        response = self.client.get("/api/tagging/stats")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_photos"], 2)
        keys = {row["key"] for row in body["tagging"]}
        self.assertIn("siglip2", keys)
        self.assertIn("places365", keys)
        caption_keys = {row["key"] for row in body["captions"]}
        self.assertIn("im2txt", caption_keys)

    @patch("api.views.tagging.AsyncTask")
    def test_retag_photos_queues_generate_tags_retag(self, async_task):
        response = self.client.post(
            "/api/retagphotos",
            {
                "tagging_model": "siglip2",
                "mode": "missing_only",
                "directory_prefix": "09/dinner",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["status"])
        async_task.assert_called_once()
        args = async_task.call_args[0]
        self.assertEqual(args[0].__name__, "generate_tags_retag")

    def test_photos_for_retag_respects_missing_only(self):
        from api import tagging

        tagged = create_test_photo(
            owner=self.user,
            captions_json={"siglip2": {"tags": ["x"]}},
        )
        untagged = create_test_photo(owner=self.user, captions_json={"places365": {}})

        missing = tagging.photos_for_retag(
            self.user, "siglip2", force=False, directory_prefix=None
        )
        ids = set(missing.values_list("pk", flat=True))
        self.assertIn(untagged.pk, ids)
        self.assertNotIn(tagged.pk, ids)
