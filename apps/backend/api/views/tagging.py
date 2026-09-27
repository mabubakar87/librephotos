import uuid

from constance import config as site_config
from django_q.tasks import AsyncTask
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api import tagging
from api.directory_watcher.processing_jobs import generate_tags_retag
from api.ml_models import do_all_models_exist, download_models
from api.models import User
from api.models.long_running_job import LongRunningJob


class TaggingStatsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(tagging.compute_tagging_stats(request.user))


class TaggingModelsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        models = [
            {"id": model_id, "label": label}
            for model_id, label in tagging.available_tagging_models()
        ]
        return Response(
            {"models": models, "active_tagging_model": site_config.TAGGING_MODEL}
        )


class RetagPhotosView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        data = request.data or {}
        tagging_model = data.get("tagging_model")
        if not tagging_model:
            return Response(
                {"status": False, "message": "tagging_model is required"},
                status=400,
            )

        allowed = {m[0] for m in tagging.available_tagging_models()}
        if tagging_model not in allowed:
            return Response(
                {"status": False, "message": f"Unknown tagging model {tagging_model!r}"},
                status=400,
            )

        mode = data.get("mode", "missing_only")
        if mode not in ("missing_only", "retag_all"):
            return Response(
                {"status": False, "message": "mode must be missing_only or retag_all"},
                status=400,
            )
        force = mode == "retag_all"
        directory_prefix = data.get("directory_prefix") or None

        if LongRunningJob.objects.filter(
            started_by=request.user,
            job_type=LongRunningJob.JOB_GENERATE_TAGS,
            finished=False,
        ).exists():
            return Response(
                {
                    "status": False,
                    "message": "A Generate Tags job is already running",
                },
                status=409,
            )

        if not do_all_models_exist():
            AsyncTask(download_models, User.objects.get(id=request.user.id)).run()

        job_id = uuid.uuid4()
        AsyncTask(
            generate_tags_retag,
            request.user,
            job_id,
            tagging_model,
            force,
            directory_prefix,
        ).run()
        return Response({"status": True, "job_id": str(job_id)})
