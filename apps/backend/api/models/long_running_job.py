import logging
import uuid
from datetime import datetime, timedelta

from django.db import models
from django.utils import timezone

from api.models.user import User, get_deleted_user

logger = logging.getLogger(__name__)


class LongRunningJob(models.Model):
    STUCK_JOB_HOURS = 24

    JOB_SCAN_PHOTOS = 1
    JOB_GENERATE_AUTO_ALBUMS = 2
    JOB_GENERATE_AUTO_ALBUM_TITLES = 3
    JOB_TRAIN_FACES = 4
    JOB_DELETE_MISSING_PHOTOS = 5
    JOB_CALCULATE_CLIP_EMBEDDINGS = 6
    JOB_SCAN_FACES = 7
    JOB_CLUSTER_ALL_FACES = 8
    JOB_DOWNLOAD_PHOTOS = 9
    JOB_DOWNLOAD_MODELS = 10
    JOB_ADD_GEOLOCATION = 11
    JOB_GENERATE_TAGS = 12
    JOB_GENERATE_FACE_EMBEDDINGS = 13
    JOB_SCAN_MISSING_PHOTOS = 14
    JOB_DETECT_DUPLICATES = 15
    JOB_REPAIR_FILE_VARIANTS = 16
    JOB_CLASSIFY_MEDIA = 17
    JOB_GENERATE_OCR = 18

    JOB_TYPES = (
        (JOB_SCAN_PHOTOS, "Scan Photos"),
        (JOB_GENERATE_AUTO_ALBUMS, "Generate Event Albums"),
        (JOB_GENERATE_AUTO_ALBUM_TITLES, "Regenerate Event Titles"),
        (JOB_TRAIN_FACES, "Train Faces"),
        (JOB_DELETE_MISSING_PHOTOS, "Delete Missing Photos"),
        (JOB_SCAN_FACES, "Scan Faces"),
        (JOB_CALCULATE_CLIP_EMBEDDINGS, "Calculate Clip Embeddings"),
        (JOB_CLUSTER_ALL_FACES, "Find Similar Faces"),
        (JOB_DOWNLOAD_PHOTOS, "Download Selected Photos"),
        (JOB_DOWNLOAD_MODELS, "Download Models"),
        (JOB_ADD_GEOLOCATION, "Add Geolocation"),
        (JOB_GENERATE_TAGS, "Generate Tags"),
        (JOB_GENERATE_FACE_EMBEDDINGS, "Generate Face Embeddings"),
        (JOB_SCAN_MISSING_PHOTOS, "Scan Missing Photos"),
        (JOB_DETECT_DUPLICATES, "Detect Duplicate Photos"),
        (JOB_REPAIR_FILE_VARIANTS, "Repair File Variants"),
        (JOB_CLASSIFY_MEDIA, "Classify Media Categories"),
        (JOB_GENERATE_OCR, "Extract Text (OCR)"),
    )

    job_type = models.PositiveIntegerField(
        choices=JOB_TYPES,
    )

    finished = models.BooleanField(default=False, blank=False, null=False)
    failed = models.BooleanField(default=False, blank=False, null=False)
    cancelled = models.BooleanField(default=False, blank=False, null=False)
    job_id = models.CharField(max_length=36, unique=True, db_index=True)
    queued_at = models.DateTimeField(default=datetime.now, null=False)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    started_by = models.ForeignKey(
        User, on_delete=models.SET(get_deleted_user), default=None
    )
    progress_current = models.PositiveIntegerField(default=0)
    progress_target = models.PositiveIntegerField(default=0)
    # New fields for detailed progress reporting
    progress_step = models.CharField(
        max_length=100, null=True, blank=True
    )  # Current step description
    result = models.JSONField(null=True, blank=True)  # Detailed result/progress data

    class Meta:
        ordering = ["-queued_at"]
        verbose_name = "Long Running Job"
        verbose_name_plural = "Long Running Jobs"

    def __str__(self):
        status = (
            "failed"
            if self.failed
            else (
                "finished"
                if self.finished
                else "running"
                if self.started_at
                else "queued"
            )
        )
        return f"Job {self.job_id} - {self.get_job_type_display()} - {status}"

    @property
    def is_running(self):
        """Check if job is currently running (started but not finished)."""
        return self.started_at is not None and not self.finished

    @property
    def duration(self):
        """Return job duration in seconds, or None if not started."""
        if not self.started_at:
            return None
        end = self.finished_at or timezone.now()
        return (end - self.started_at).total_seconds()

    def _update_row(self, *, only_if_running=False, **fields):
        """
        Persist field updates with QuerySet.update to avoid
        'Save with update_fields did not affect any rows' on stale instances.
        """
        if not self.pk:
            logger.warning("LongRunningJob has no pk; skip update")
            return False

        qs = LongRunningJob.objects.filter(pk=self.pk)
        if only_if_running:
            qs = qs.filter(finished=False)

        rows = qs.update(**fields)
        if rows:
            for name, value in fields.items():
                setattr(self, name, value)
            return True

        if not LongRunningJob.objects.filter(pk=self.pk).exists():
            logger.warning("LongRunningJob pk=%s deleted; skip update", self.pk)
        return False

    def start(self):
        """Mark job as started."""
        started_at = timezone.now()
        if self._update_row(started_at=started_at):
            return
        self.started_at = started_at
        self.save(update_fields=["started_at"])

    def complete(self, result=None):
        """Mark job as successfully completed."""
        fields = {
            "finished": True,
            "finished_at": timezone.now(),
        }
        if result is not None:
            fields["result"] = result
        if self._update_row(**fields):
            return
        self.finished = fields["finished"]
        self.finished_at = fields["finished_at"]
        if result is not None:
            self.result = result
        self.save(update_fields=["finished", "finished_at", "result"])

    def fail(self, error=None):
        """Mark job as failed with optional error message."""
        fields = {
            "failed": True,
            "finished": True,
            "finished_at": timezone.now(),
        }
        if error is not None:
            fields["result"] = {"status": "failed", "error": str(error)}
        if self._update_row(**fields):
            return
        self.failed = fields["failed"]
        self.finished = fields["finished"]
        self.finished_at = fields["finished_at"]
        if error is not None:
            self.result = fields["result"]
        self.save(update_fields=["failed", "finished", "finished_at", "result"])

    def cancel(self):
        """Mark job as cancelled and finished."""
        fields = {
            "cancelled": True,
            "finished": True,
            "finished_at": timezone.now(),
            "result": {"status": "cancelled"},
        }
        if self._update_row(**fields):
            return
        self.cancelled = True
        self.finished = True
        self.finished_at = fields["finished_at"]
        self.result = fields["result"]
        self.save(update_fields=["cancelled", "finished", "finished_at", "result"])

    def update_progress(self, current, target=None, step=None):
        """Update job progress counters and optional step description."""
        fields = {"progress_current": current}
        if target is not None:
            fields["progress_target"] = target
        if step is not None:
            fields["progress_step"] = step
        self._update_row(only_if_running=True, **fields)

    def set_result(self, result):
        """Update the job result/progress data."""
        self._update_row(only_if_running=True, result=result)

    @classmethod
    def create_job(cls, user, job_type, job_id=None, start_now=False):
        """
        Factory method to create a new job with proper defaults.

        Args:
            user: The user who started the job
            job_type: One of the JOB_* constants
            job_id: Optional job ID (auto-generated UUID if not provided)
            start_now: If True, set started_at to now

        Returns:
            The newly created LongRunningJob instance
        """
        if job_id is None:
            job_id = str(uuid.uuid4())
        job = cls.objects.create(
            started_by=user,
            job_id=str(job_id),
            queued_at=timezone.now(),
            job_type=job_type,
        )
        if start_now:
            job.start()
        return job

    @classmethod
    def get_or_create_job(cls, user, job_type, job_id):
        """
        Get an existing job by job_id or create a new one.

        This is useful for queued jobs where the job_id is known ahead of time.
        If the job exists, it will be marked as started. If not, a new job is created.

        Args:
            user: The user who started the job
            job_type: One of the JOB_* constants
            job_id: The job ID to look up or use for creation

        Returns:
            The LongRunningJob instance (existing or newly created)
        """
        if cls.objects.filter(job_id=job_id).exists():
            job = cls.objects.get(job_id=job_id)
            job.start()
            return job
        return cls.create_job(
            user=user, job_type=job_type, job_id=job_id, start_now=True
        )

    @classmethod
    def cleanup_stuck_jobs(cls, hours=None):
        """
        Mark jobs as failed if they've been running (or queued) for too long.

        Jobs with finished=False are considered stuck when:
        - started_at is set and older than the threshold, or
        - started_at is null and queued_at is older than the threshold
          (never-started orphans from crashed workers).

        Args:
            hours: Hours after which a job is considered stuck.
                Defaults to STUCK_JOB_HOURS.

        Returns:
            Number of jobs marked as failed
        """
        if hours is None:
            hours = cls.STUCK_JOB_HOURS
        cutoff = timezone.now() - timedelta(hours=hours)
        stuck_jobs = cls.objects.filter(finished=False).filter(
            models.Q(started_at__isnull=False, started_at__lt=cutoff)
            | models.Q(started_at__isnull=True, queued_at__lt=cutoff)
        )
        count = stuck_jobs.count()
        stuck_jobs.update(
            failed=True,
            finished=True,
            finished_at=timezone.now(),
            result={"status": "failed", "error": f"Job timed out after {hours} hours"},
        )
        return count

    @classmethod
    def cleanup_old_jobs(cls, days=30):
        """
        Delete completed/failed jobs older than specified days, but always keep
        the most recent finished job of each (user, job_type).

        The latest finished job per type is preserved regardless of age because
        the incremental scan uses it as the "last scan" baseline: it is queried
        in ``api/directory_watcher/scan_jobs.py`` and ``processing_jobs.py`` to
        decide which photos can be skipped. Deleting it leaves no baseline, so
        the next scan reprocesses (and re-enriches) the entire library. Older
        finished jobs of the same type are still pruned as litter.

        Args:
            days: Number of days after which surplus completed jobs are deleted

        Returns:
            Number of jobs deleted
        """
        cutoff = timezone.now() - timedelta(days=days)

        # Preserve the most recent finished job of each (user, job_type) — the
        # incremental-scan baseline — at any age. The number of groups is
        # bounded by users x job types, so this loop is cheap.
        keep_ids = set()
        groups = (
            cls.objects.filter(finished=True, finished_at__isnull=False)
            .values_list("started_by_id", "job_type")
            .distinct()
        )
        for started_by_id, job_type in groups:
            latest_id = (
                cls.objects.filter(
                    finished=True,
                    finished_at__isnull=False,
                    started_by_id=started_by_id,
                    job_type=job_type,
                )
                .order_by("-finished_at", "-id")
                .values_list("id", flat=True)
                .first()
            )
            if latest_id is not None:
                keep_ids.add(latest_id)

        deleted, _ = (
            cls.objects.filter(finished=True, finished_at__lt=cutoff)
            .exclude(id__in=keep_ids)
            .delete()
        )
        return deleted
