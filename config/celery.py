"""
Celery application instance untuk Simple LMS.

File ini HARUS diimport di config/__init__.py supaya Celery
terdeteksi saat Django start.

Referensi: https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
"""
import os
from celery import Celery

# Set default settings module untuk program 'celery'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('simple_lms')

# Baca konfigurasi dari Django settings, prefix CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks dari semua INSTALLED_APPS
# Django akan mencari file tasks.py di setiap app
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Task diagnostic: print request info ke log Celery worker."""
    print(f'Request: {self.request!r}')
