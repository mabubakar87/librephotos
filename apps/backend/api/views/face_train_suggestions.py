"""Train face classifiers from labels without re-clustering (GPU-mount friendly)."""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django_q.tasks import Chain
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.directory_watcher import generate_face_embeddings
from api.face_classify import train_faces
from api.ml_models import do_all_models_exist, download_models
from api.models.long_running_job import LongRunningJob

logger = logging.getLogger(__name__)


def face_background_job_running(user) -> bool:
    cutoff = timezone.now() - timedelta(hours=LongRunningJob.STUCK_JOB_HOURS)
    return (
        LongRunningJob.objects.filter(
            started_by=user,
            finished=False,
            job_type__in=(
                LongRunningJob.JOB_TRAIN_FACES,
                LongRunningJob.JOB_CLUSTER_ALL_FACES,
                LongRunningJob.JOB_GENERATE_FACE_EMBEDDINGS,
            ),
        )
        .filter(
            Q(started_at__gte=cutoff)
            | Q(started_at__isnull=True, queued_at__gte=cutoff)
        )
        .exists()
    )


class TrainFaceSuggestionsView(APIView):
    def post(self, request, format=None):
        if not settings.FEATURE_FACE_CLUSTER:
            return Response(
                {"status": False, "message": "Face clustering is disabled"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if face_background_job_running(request.user):
            return Response(
                {
                    "status": False,
                    "message": "A face training or clustering job is already running",
                },
                status=status.HTTP_409_CONFLICT,
            )

        job_id = uuid.uuid4()
        try:
            chain = Chain()
            if not do_all_models_exist():
                chain.append(download_models, request.user)
            chain.append(generate_face_embeddings, request.user, uuid.uuid4())
            chain.append(train_faces, request.user, job_id)
            chain.run()
        except Exception:
            logger.exception("Could not start face suggestion training")
            return Response(
                {
                    "status": False,
                    "message": "Could not start face suggestion training.",
                },
                status=500,
            )
        return Response({"status": True, "job_id": job_id})
