"""
Redis Caching & Rate Limiting untuk Simple LMS API.

Modul ini mengelola:
1. Cache key builder  → format key yang konsisten, mudah di-invalidate
2. get/set course list cache
3. get/set course detail cache
4. invalidate_course_cache → dipanggil saat course create/update/delete
5. check_rate_limit → dekorator sliding-window rate limiter (60 req/menit)

Semua operasi Redis menggunakan django-redis via Django CACHES,
sehingga tidak perlu koneksi Redis langsung — cukup `from django.core.cache import cache`.
"""
import json
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from ninja.errors import HttpError


# ============================================================
# CACHE KEY BUILDER
# ============================================================
def _key_course_list(page: int, page_size: int, search: str, category_id, instructor_id) -> str:
    """
    Key unik untuk list courses. Semua parameter pagination & filter
    dimasukkan ke key supaya setiap kombinasi berbeda tidak saling menimpa.
    """
    return (
        f"course:list:"
        f"p{page}:ps{page_size}:"
        f"s{search or ''}:"
        f"cat{category_id or ''}:"
        f"inst{instructor_id or ''}"
    )


def _key_course_detail(course_id: int) -> str:
    return f"course:detail:{course_id}"


def _key_rate_limit(ip: str) -> str:
    return f"ratelimit:{ip}"


# ============================================================
# COURSE LIST CACHE
# ============================================================
def get_cached_course_list(page, page_size, search, category_id, instructor_id):
    """
    Ambil course list dari Redis cache.
    Return dict (cached) atau None (cache miss).
    """
    key = _key_course_list(page, page_size, search, category_id, instructor_id)
    cached = cache.get(key)
    if cached:
        print(f"[CACHE HIT] {key}")
    else:
        print(f"[CACHE MISS] {key}")
    return cached


def set_cached_course_list(data: dict, page, page_size, search, category_id, instructor_id):
    """Simpan course list ke Redis dengan TTL dari settings."""
    key = _key_course_list(page, page_size, search, category_id, instructor_id)
    ttl = getattr(settings, 'CACHE_TTL_COURSE_LIST', 300)
    cache.set(key, data, timeout=ttl)
    print(f"[CACHE SET] {key} (TTL={ttl}s)")


# ============================================================
# COURSE DETAIL CACHE
# ============================================================
def get_cached_course_detail(course_id: int):
    """Return cached course detail dict atau None."""
    key = _key_course_detail(course_id)
    cached = cache.get(key)
    if cached:
        print(f"[CACHE HIT] {key}")
    else:
        print(f"[CACHE MISS] {key}")
    return cached


def set_cached_course_detail(data: dict, course_id: int):
    """Simpan course detail ke Redis dengan TTL dari settings."""
    key = _key_course_detail(course_id)
    ttl = getattr(settings, 'CACHE_TTL_COURSE_DETAIL', 600)
    cache.set(key, data, timeout=ttl)
    print(f"[CACHE SET] {key} (TTL={ttl}s)")


# ============================================================
# CACHE INVALIDATION STRATEGY
# ============================================================
def invalidate_course_cache(course_id: int):
    """
    Cache Invalidation Strategy:

    Saat course create / update / delete, kita tidak bisa tahu kombinasi
    filter mana yang sudah di-cache. Strategi yang dipilih:

    1. Hapus SEMUA key dengan prefix "lms:course:list:*" menggunakan
       django-redis delete_pattern (wildcard scan).
    2. Hapus key detail course yang bersangkutan.

    Trade-off: pendekatan ini lebih sederhana dan aman daripada mencoba
    track setiap kombinasi yang ter-cache. Downside: next request akan
    hit DB, tapi ini justru yang kita inginkan supaya data selalu fresh.
    """
    # Hapus detail cache
    detail_key = f"lms:{_key_course_detail(course_id)}"
    cache.delete(_key_course_detail(course_id))
    print(f"[CACHE INVALIDATE] course detail id={course_id}")

    # Hapus semua course list cache (perlu django-redis delete_pattern)
    try:
        from django_redis import get_redis_connection
        con = get_redis_connection("default")
        keys = con.keys("lms:course:list:*")
        if keys:
            con.delete(*keys)
            print(f"[CACHE INVALIDATE] {len(keys)} course list key(s)")
    except Exception as e:
        # Fallback: kalau delete_pattern tidak tersedia, biarkan cache expire
        print(f"[CACHE INVALIDATE WARNING] {e}")


# ============================================================
# RATE LIMITING (Sliding Window, 60 req / menit)
# ============================================================
def check_rate_limit(request):
    """
    Implementasi sliding-window rate limiter dengan Redis.

    Algoritma:
    1. Key  = "ratelimit:<ip>" dengan nilai = counter integer
    2. Setiap request: INCR counter
    3. Kalau counter == 1 (pertama kali): set TTL = RATE_LIMIT_WINDOW detik
    4. Kalau counter > RATE_LIMIT_REQUESTS: raise HttpError 429

    Kenapa sliding window sederhana ini cukup:
    - Redis INCR bersifat atomic → tidak ada race condition
    - TTL otomatis reset window setiap 1 menit
    - Untuk production yang butuh presisi lebih tinggi, pakai Redis sorted set
    """
    ip = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR', '127.0.0.1')
    )
    key   = _key_rate_limit(ip)
    limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 60)
    window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)

    count = cache.get(key, 0)
    count += 1

    if count == 1:
        cache.set(key, count, timeout=window)
    else:
        # Ambil sisa TTL supaya tidak reset tiap request
        cache.set(key, count, timeout=cache.ttl(key) if hasattr(cache, 'ttl') else window)

    print(f"[RATE LIMIT] ip={ip} count={count}/{limit}")

    if count > limit:
        raise HttpError(
            429,
            f"Terlalu banyak request. Coba lagi dalam {window} detik."
        )


def rate_limit(view_func):
    """
    Decorator untuk menerapkan rate limiting ke satu endpoint.
    Dipasang DI BAWAH decorator route (dieksekusi lebih awal).

    Contoh:
        @courses_router.get("", response=...)
        @rate_limit
        def list_courses(request, ...):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        check_rate_limit(request)
        return view_func(request, *args, **kwargs)
    return wrapper
