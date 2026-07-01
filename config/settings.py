"""
Django settings for config project - Simple LMS.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ====================
# SECURITY
# ====================
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-r^n_lb209p)ea!o!7zet#%xj7k^d01uc24*q69#%)j@gxips^1')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

# ====================
# APPLICATIONS
# ====================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'ninja',
    'lms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ====================
# DATABASE (PostgreSQL)
# ====================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB'),
        'USER': os.getenv('POSTGRES_USER'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
        'HOST': os.getenv('POSTGRES_HOST', 'db'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}

# ====================
# CUSTOM AUTH
# ====================
AUTH_USER_MODEL = 'lms.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ====================
# JWT
# ====================
JWT_SECRET_KEY = SECRET_KEY
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_TOKEN_LIFETIME_MINUTES = 30
JWT_REFRESH_TOKEN_LIFETIME_DAYS = 7

# ====================
# REDIS CACHE
# ====================
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'TIMEOUT': 300,   # default 5 menit
        'KEY_PREFIX': 'lms',
    }
}

# TTL khusus per resource (detik)
CACHE_TTL_COURSE_LIST   = 300   # 5 menit
CACHE_TTL_COURSE_DETAIL = 600   # 10 menit

# Rate Limiting
RATE_LIMIT_REQUESTS = 60   # max request
RATE_LIMIT_WINDOW   = 60   # per detik (1 menit)

# ====================
# MONGODB
# ====================
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://mongodb:27017')
MONGO_DB  = os.getenv('MONGO_DB',  'lms_analytics')

# ====================
# CELERY
# ====================
CELERY_BROKER_URL        = os.getenv('CELERY_BROKER_URL', 'amqp://guest:guest@rabbitmq:5672//')
CELERY_RESULT_BACKEND    = REDIS_URL
CELERY_ACCEPT_CONTENT    = ['json']
CELERY_TASK_SERIALIZER   = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE          = 'UTC'

# Celery Beat: jadwal task periodik
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'update-course-statistics-every-hour': {
        'task': 'lms.tasks.update_course_statistics',
        'schedule': crontab(minute=0),  # setiap awal jam
    },
}

# ====================
# EMAIL
# ====================
EMAIL_BACKEND      = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST         = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT         = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS      = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER    = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD= os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@simplelms.com')

# ====================
# STATIC / I18N
# ====================
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'UTC'
USE_I18N      = True
USE_TZ        = True
STATIC_URL    = 'static/'
MEDIA_ROOT    = BASE_DIR / 'media'
MEDIA_URL     = '/media/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
