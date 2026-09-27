"""Tagging coverage stats and photo selection for retag jobs."""

import os

from django.conf import settings
from django.db.models import Q

from api.models import Photo

# Keys that store scene tags (Things albums), including retired models.
TAGGING_MODEL_KEYS = frozenset(
    {
        "mobileclip_s2",
        "siglip2",
        "places365",
    }
)

# Caption / LLM keys shown separately from scene tagging.
CAPTION_MODEL_KEYS = frozenset(
    {
        "im2txt",
        "moondream",
        "lfm2_vl_450m",
        "user_caption",
    }
)


def available_tagging_models():
    """Tagging model ids the user can pick for a retag job."""
    field = settings.CONSTANCE_ADDITIONAL_FIELDS.get("tagging_model")
    choices = None
    if isinstance(field, (list, tuple)):
        for item in field:
            if isinstance(item, dict) and item.get("choices"):
                choices = item["choices"]
                break
    if not choices:
        return [("mobileclip_s2", "MobileCLIP-S2"), ("siglip2", "SigLIP 2")]
    return list(choices)


def _photo_base_qs(user):
    return Photo.objects.filter(owner=user, hidden=False, in_trashcan=False)


def compute_tagging_stats(user):
    """Return counts and percentages for tagging and caption keys."""
    total = _photo_base_qs(user).count()
    if total == 0:
        return {
            "total_photos": 0,
            "tagging": [],
            "captions": [],
            "untagged_scene": 0,
            "untagged_scene_percent": 0,
        }

    def _rows(keys):
        rows = []
        for key in keys:
            count = _photo_base_qs(user).filter(
                caption_instance__captions_json__has_key=key
            ).count()
            if count == 0:
                continue
            rows.append(
                {
                    "key": key,
                    "count": count,
                    "percent": round(100.0 * count / total, 2),
                }
            )
        rows.sort(key=lambda row: (-row["count"], row["key"]))
        return rows

    tagging_rows = _rows(TAGGING_MODEL_KEYS)
    any_scene_tag = (
        _photo_base_qs(user)
        .filter(
            Q(caption_instance__captions_json__has_key="mobileclip_s2")
            | Q(caption_instance__captions_json__has_key="siglip2")
            | Q(caption_instance__captions_json__has_key="places365")
        )
        .count()
    )

    return {
        "total_photos": total,
        "tagging": tagging_rows,
        "captions": _rows(CAPTION_MODEL_KEYS),
        "untagged_scene": total - any_scene_tag,
        "untagged_scene_percent": round(100.0 * (total - any_scene_tag) / total, 2),
    }


def normalize_directory_prefix(user, directory_prefix: str | None) -> str | None:
    if not directory_prefix or not str(directory_prefix).strip():
        return None
    raw = str(directory_prefix).strip().replace("\\", "/")
    if raw.startswith("/"):
        return raw.rstrip("/") + "/"
    base = (user.scan_directory or "/data").rstrip("/")
    return f"{base}/{raw.lstrip('/')}".rstrip("/") + "/"


def photos_for_retag(
    user,
    tagging_model: str,
    *,
    force: bool,
    directory_prefix: str | None = None,
):
    qs = _photo_base_qs(user).filter(thumbnail__isnull=False)
    prefix = normalize_directory_prefix(user, directory_prefix)
    if prefix:
        qs = qs.filter(main_file__path__startswith=prefix)

    if not force:
        qs = qs.filter(
            Q(caption_instance__isnull=True)
            | Q(caption_instance__captions_json__isnull=True)
            | Q(**{f"caption_instance__captions_json__{tagging_model}__isnull": True})
        )
    return qs.order_by("image_hash")
