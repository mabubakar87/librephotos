from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from api.face_person_deduplication import dedupe_all_person_assignments_per_photo


class Command(BaseCommand):
    help = (
        "Remove duplicate person labels on the same photo, keeping the face "
        "with the highest match probability."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            help="Only process photos owned by this user.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report duplicates without changing the database.",
        )

    def handle(self, *args, **options):
        owner_id = None
        username = options.get("username")
        if username:
            user = get_user_model().objects.filter(username=username).first()
            if user is None:
                self.stderr.write(f"No user named {username!r}\n")
                return
            owner_id = user.id

        label_result, suggestion_result = dedupe_all_person_assignments_per_photo(
            owner_id=owner_id,
            dry_run=options["dry_run"],
        )
        prefix = "Would" if options["dry_run"] else ""
        self.stdout.write(
            f"{prefix} Unlabeled {label_result.faces_unlabeled} duplicate "
            f"confirmed label(s) in {label_result.duplicate_groups} group(s).\n"
            f"{prefix} Cleared {suggestion_result.suggestions_cleared} duplicate "
            f"inferred name(s) in {suggestion_result.duplicate_groups} group(s).\n"
        )
