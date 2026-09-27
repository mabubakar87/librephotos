from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.tests.utils import create_test_user


class TrainFaceSuggestionsApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_test_user()
        self.client.force_authenticate(user=self.user)

    @patch("api.views.face_train_suggestions.do_all_models_exist", return_value=True)
    @patch("api.views.face_train_suggestions.Chain")
    def test_suggestions_queues_train_only_pipeline(self, chain_cls, _models_ok):
        chain = MagicMock()
        chain_cls.return_value = chain

        response = self.client.post("/api/trainfaces/suggestions", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["status"])
        chain.append.assert_called()
        chain.run.assert_called_once()
