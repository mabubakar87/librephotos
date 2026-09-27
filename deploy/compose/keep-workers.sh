#!/bin/bash
# Restart the background worker if it exits, and release tasks that a dead
# worker left locked. LibrePhotos sets django-q retry to 20,000,000 seconds,
# so a task taken by a worker that then dies is hidden until that lock expires.
sleep 180
while true; do
  if ! ps -eo args | grep -q "[m]anage.py qcluster"; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) qcluster is not running; releasing locks from the dead worker and starting it"
    # Only unlock when the cluster is actually gone. A live CLIP job holds its
    # lock for hours and never writes a finished Task row until the end, so
    # releasing that lock while qcluster is up starts a second copy of the same job.
    (cd /code && python manage.py shell <<'PY'
from datetime import timedelta
from django.utils import timezone
from django_q.models import OrmQ
released = OrmQ.objects.filter(lock__gt=timezone.now()).update(
    lock=timezone.now() - timedelta(seconds=1)
)
print("released locks:", released)
PY
)
    (cd /code && python manage.py qcluster >> /logs/qcluster.log 2>&1) &
  fi
  sleep 300
done
