"""Ensure at most one face per person on each photo (labels and suggestions).

Duplicate assignments can come from repeated manual labels, bad imports,
classification on many detections in one group photo, or confirming inferred
faces more than once. The strongest match is kept; others are cleared (face
rows are kept).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from api.models.face import Face
from api.models.person import Person

logger = logging.getLogger(__name__)

# Manual labels (person set without matching classification) beat inferred ties.
MANUAL_LABEL_SCORE = 1.0


@dataclass
class PersonPerPhotoDedupeResult:
    photos_processed: int = 0
    duplicate_groups: int = 0
    faces_unlabeled: int = 0
    cleared_face_ids: list[int] = field(default_factory=list)
    affected_photo_ids: list[int] = field(default_factory=list)
    affected_person_ids: list[int] = field(default_factory=list)


@dataclass
class ClassificationPerPhotoDedupeResult:
    photos_processed: int = 0
    duplicate_groups: int = 0
    suggestions_cleared: int = 0
    cleared_face_ids: list[int] = field(default_factory=list)
    affected_photo_ids: list[int] = field(default_factory=list)


def person_label_score(face: Face) -> tuple[float, int, int]:
    """Sort key: higher keeps the face. Uses probability, then box area, then id."""
    if face.person_id is None:
        return (-1.0, 0, face.id)
    if face.classification_person_id == face.person_id:
        score = float(face.classification_probability or 0.0)
    else:
        score = MANUAL_LABEL_SCORE
    area = max(
        0,
        (face.location_bottom - face.location_top)
        * (face.location_right - face.location_left),
    )
    return (score, area, -face.id)


def classification_suggestion_score(face: Face, person_id: int) -> tuple[float, int, int]:
    """Sort key for which face keeps an inferred name on a photo."""
    if face.person_id == person_id:
        return person_label_score(face)
    return (
        float(face.classification_probability or 0.0),
        max(
            0,
            (face.location_bottom - face.location_top)
            * (face.location_right - face.location_left),
        ),
        -face.id,
    )


def dedupe_labeled_persons_per_photo(
    *,
    photo_ids: Iterable[int] | None = None,
    owner_id: int | None = None,
    dry_run: bool = False,
) -> PersonPerPhotoDedupeResult:
    """Clear duplicate ``person`` assignments on the same photo.

    When several faces on one photo share the same ``person_id``, the face with
    the highest classification probability (for that person) is kept. Manual
    labels count as certainty when ``classification_person`` does not match.
    """
    result = PersonPerPhotoDedupeResult()
    faces_qs = Face.objects.filter(person_id__isnull=False, deleted=False)
    if photo_ids is not None:
        faces_qs = faces_qs.filter(photo_id__in=photo_ids)
    if owner_id is not None:
        faces_qs = faces_qs.filter(photo__owner_id=owner_id)

    faces_qs = faces_qs.only(
        "id",
        "photo_id",
        "person_id",
        "classification_person_id",
        "classification_probability",
        "location_top",
        "location_bottom",
        "location_left",
        "location_right",
    )

    by_photo_person: dict[tuple[int, int], list[Face]] = defaultdict(list)
    for face in faces_qs.iterator(chunk_size=2000):
        by_photo_person[(face.photo_id, face.person_id)].append(face)

    to_clear: list[int] = []
    affected_photos: set[int] = set()
    affected_persons: set[int] = set()

    for (photo_id, person_id), group in by_photo_person.items():
        result.photos_processed += 1
        if len(group) < 2:
            continue
        result.duplicate_groups += 1
        group.sort(key=person_label_score, reverse=True)
        keeper = group[0]
        for duplicate in group[1:]:
            to_clear.append(duplicate.id)
            affected_photos.add(photo_id)
            affected_persons.add(person_id)
            logger.info(
                "Duplicate person label: photo=%s person=%s keep face=%s "
                "(score=%s) unlabel face=%s (score=%s)",
                photo_id,
                person_id,
                keeper.id,
                person_label_score(keeper)[0],
                duplicate.id,
                person_label_score(duplicate)[0],
            )

    result.faces_unlabeled = len(to_clear)
    result.cleared_face_ids = to_clear
    result.affected_photo_ids = sorted(affected_photos)
    result.affected_person_ids = sorted(affected_persons)

    if to_clear and not dry_run:
        Face.objects.filter(id__in=to_clear).update(person_id=None)
        for person in Person.objects.filter(id__in=affected_persons):
            person._calculate_face_count()
            person._set_default_cover_photo()

    return result


def dedupe_classification_suggestions_per_photo(
    *,
    photo_ids: Iterable[int] | None = None,
    owner_id: int | None = None,
    dry_run: bool = False,
) -> ClassificationPerPhotoDedupeResult:
    """Clear duplicate inferred names (``classification_person``) on the same photo.

    The photo sidebar lists every face and shows ``classification_person`` when
    there is no manual ``person`` label, so many false positives for one name
    look like repeated tags. At most one face per photo keeps each suggested
    person; confirmed ``person`` labels win over inference-only rows.
    """
    result = ClassificationPerPhotoDedupeResult()
    faces_qs = Face.objects.filter(
        classification_person_id__isnull=False,
        deleted=False,
    )
    if photo_ids is not None:
        faces_qs = faces_qs.filter(photo_id__in=photo_ids)
    if owner_id is not None:
        faces_qs = faces_qs.filter(photo__owner_id=owner_id)

    faces_qs = faces_qs.only(
        "id",
        "photo_id",
        "person_id",
        "classification_person_id",
        "classification_probability",
        "cluster_person_id",
        "cluster_probability",
        "location_top",
        "location_bottom",
        "location_left",
        "location_right",
    )

    by_photo_person: dict[tuple[int, int], list[Face]] = defaultdict(list)
    for face in faces_qs.iterator(chunk_size=2000):
        by_photo_person[(face.photo_id, face.classification_person_id)].append(face)

    to_clear: list[tuple[int, int]] = []  # (face_id, classification_person_id)
    affected_photos: set[int] = set()

    for (photo_id, person_id), group in by_photo_person.items():
        result.photos_processed += 1
        if len(group) < 2:
            continue
        result.duplicate_groups += 1
        group.sort(
            key=lambda face: classification_suggestion_score(face, person_id),
            reverse=True,
        )
        keeper = group[0]
        for duplicate in group[1:]:
            to_clear.append((duplicate.id, person_id))
            affected_photos.add(photo_id)
            logger.info(
                "Duplicate classification: photo=%s person=%s keep face=%s "
                "(score=%s) clear face=%s (score=%s)",
                photo_id,
                person_id,
                keeper.id,
                classification_suggestion_score(keeper, person_id)[0],
                duplicate.id,
                classification_suggestion_score(duplicate, person_id)[0],
            )

    result.suggestions_cleared = len(to_clear)
    result.cleared_face_ids = [face_id for face_id, _ in to_clear]
    result.affected_photo_ids = sorted(affected_photos)

    if to_clear and not dry_run:
        face_ids = [face_id for face_id, _ in to_clear]
        Face.objects.filter(id__in=face_ids).update(
            classification_person_id=None,
            classification_probability=0.0,
        )
        cleared_by_person: dict[int, list[int]] = defaultdict(list)
        for face_id, person_id in to_clear:
            cleared_by_person[person_id].append(face_id)
        for person_id, ids in cleared_by_person.items():
            Face.objects.filter(id__in=ids, cluster_person_id=person_id).update(
                cluster_person_id=None,
                cluster_probability=0.0,
            )

    return result


def dedupe_all_person_assignments_per_photo(
    *,
    photo_ids: Iterable[int] | None = None,
    owner_id: int | None = None,
    dry_run: bool = False,
) -> tuple[PersonPerPhotoDedupeResult, ClassificationPerPhotoDedupeResult]:
    """Run labeled-person dedupe, then inferred-name dedupe."""
    label_result = dedupe_labeled_persons_per_photo(
        photo_ids=photo_ids,
        owner_id=owner_id,
        dry_run=dry_run,
    )
    suggestion_result = dedupe_classification_suggestions_per_photo(
        photo_ids=photo_ids,
        owner_id=owner_id,
        dry_run=dry_run,
    )
    return label_result, suggestion_result
