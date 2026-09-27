from django.test import TestCase

from api.models.long_running_job import LongRunningJob
from api.tests.utils import create_test_user


class LongRunningJobPersistenceTestCase(TestCase):
    def setUp(self):
        self.user = create_test_user()

    def test_set_result_on_deleted_job_does_not_raise(self):
        job = LongRunningJob.create_job(
            user=self.user,
            job_type=LongRunningJob.JOB_DETECT_DUPLICATES,
            start_now=True,
        )
        pk = job.pk
        LongRunningJob.objects.filter(pk=pk).delete()

        job.set_result({"current": 1, "total": 10})

    def test_set_result_on_finished_job_does_not_raise_or_overwrite(self):
        job = LongRunningJob.create_job(
            user=self.user,
            job_type=LongRunningJob.JOB_DETECT_DUPLICATES,
            start_now=True,
        )
        job.complete(result={"status": "completed", "duplicates_found": 3})

        job.set_result({"stage": "visual_duplicates", "current": 99, "total": 100})

        job.refresh_from_db()
        self.assertEqual(job.result["status"], "completed")
        self.assertEqual(job.result["duplicates_found"], 3)

    def test_update_progress_uses_running_row_only(self):
        job = LongRunningJob.create_job(
            user=self.user,
            job_type=LongRunningJob.JOB_DETECT_DUPLICATES,
            start_now=True,
        )
        job.update_progress(current=5, target=100, step="visual_duplicates")

        job.refresh_from_db()
        self.assertEqual(job.progress_current, 5)
        self.assertEqual(job.progress_target, 100)
