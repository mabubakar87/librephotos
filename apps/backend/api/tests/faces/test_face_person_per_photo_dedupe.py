from django.test import TestCase
from django.utils import timezone

from api.face_person_deduplication import (
    dedupe_classification_suggestions_per_photo,
    dedupe_labeled_persons_per_photo,
    person_label_score,
)
from api.models import Face, Person, Photo, User


class FacePersonPerPhotoDedupeTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.photo = Photo.objects.create(
            owner=self.user,
            image_hash="dedupehash1",
            added_on=timezone.now(),
        )
        self.alice = Person.objects.create(name="Alice", cluster_owner=self.user)

    def _face(self, *, person, top=0, prob=0.0, classification_person=None):
        classification_person = classification_person or person
        return Face.objects.create(
            photo=self.photo,
            person=person,
            classification_person=classification_person,
            classification_probability=prob,
            location_top=top,
            location_bottom=top + 100,
            location_left=0,
            location_right=100,
            encoding="0" * 256,
        )

    def test_no_duplicates_is_noop(self):
        self._face(person=self.alice, prob=0.9)
        result = dedupe_labeled_persons_per_photo(photo_ids=[self.photo.id])
        self.assertEqual(result.faces_unlabeled, 0)
        self.assertEqual(Face.objects.filter(photo=self.photo, person=self.alice).count(), 1)

    def test_keeps_highest_classification_probability(self):
        weak = self._face(person=self.alice, top=0, prob=0.4)
        strong = self._face(person=self.alice, top=110, prob=0.95)

        result = dedupe_labeled_persons_per_photo(photo_ids=[self.photo.id])

        self.assertEqual(result.faces_unlabeled, 1)
        weak.refresh_from_db()
        strong.refresh_from_db()
        self.assertIsNone(weak.person_id)
        self.assertEqual(strong.person_id, self.alice.id)

    def test_manual_label_beats_lower_probability(self):
        inferred = self._face(
            person=self.alice,
            top=0,
            prob=0.99,
            classification_person=self.alice,
        )
        manual = self._face(
            person=self.alice,
            top=110,
            prob=0.2,
            classification_person=None,
        )

        result = dedupe_labeled_persons_per_photo(photo_ids=[self.photo.id])

        self.assertEqual(result.faces_unlabeled, 1)
        inferred.refresh_from_db()
        manual.refresh_from_db()
        self.assertIsNone(inferred.person_id)
        self.assertEqual(manual.person_id, self.alice.id)
        self.assertGreater(person_label_score(manual), person_label_score(inferred))

    def test_different_people_on_same_photo_untouched(self):
        bob = Person.objects.create(name="Bob", cluster_owner=self.user)
        self._face(person=self.alice, prob=0.8)
        self._face(person=bob, top=120, prob=0.7, classification_person=bob)

        result = dedupe_labeled_persons_per_photo(photo_ids=[self.photo.id])

        self.assertEqual(result.faces_unlabeled, 0)
        self.assertEqual(Face.objects.filter(photo=self.photo, person__isnull=False).count(), 2)

    def test_dry_run_does_not_change_database(self):
        self._face(person=self.alice, prob=0.3)
        self._face(person=self.alice, top=110, prob=0.9)

        result = dedupe_labeled_persons_per_photo(
            photo_ids=[self.photo.id],
            dry_run=True,
        )

        self.assertEqual(result.faces_unlabeled, 1)
        self.assertEqual(Face.objects.filter(photo=self.photo, person=self.alice).count(), 2)

    def test_dedupe_classification_suggestions_keeps_best_probability(self):
        weak = Face.objects.create(
            photo=self.photo,
            person=None,
            classification_person=self.alice,
            classification_probability=0.4,
            location_top=0,
            location_bottom=100,
            location_left=0,
            location_right=100,
            encoding="0" * 256,
        )
        strong = Face.objects.create(
            photo=self.photo,
            person=None,
            classification_person=self.alice,
            classification_probability=0.95,
            location_top=110,
            location_bottom=210,
            location_left=0,
            location_right=100,
            encoding="1" * 256,
        )

        result = dedupe_classification_suggestions_per_photo(photo_ids=[self.photo.id])

        self.assertEqual(result.suggestions_cleared, 1)
        weak.refresh_from_db()
        strong.refresh_from_db()
        self.assertIsNone(weak.classification_person_id)
        self.assertEqual(strong.classification_person_id, self.alice.id)
