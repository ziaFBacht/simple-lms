# Pastikan Celery app selalu di-load saat Django start,
# sehingga shared_task bisa menggunakannya.
from .celery import app as celery_app

__all__ = ('celery_app',)
