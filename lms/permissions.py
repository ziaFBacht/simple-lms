"""
Permission System untuk Simple LMS API.
"""
from functools import wraps

from ninja.errors import HttpError


def is_admin(view_func):
    """Hanya izinkan user dengan role='admin' (atau Django superuser)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.auth
        if not (getattr(user, "role", None) == "admin" or user.is_superuser):
            raise HttpError(403, "Hanya admin yang dapat mengakses endpoint ini")
        return view_func(request, *args, **kwargs)

    return wrapper


def is_instructor(view_func):
    """Hanya izinkan user dengan role='instructor'."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.auth
        if getattr(user, "role", None) != "instructor":
            raise HttpError(403, "Hanya instructor yang dapat mengakses endpoint ini")
        return view_func(request, *args, **kwargs)

    return wrapper


def is_student(view_func):
    """Hanya izinkan user dengan role='student'."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.auth
        if getattr(user, "role", None) != "student":
            raise HttpError(403, "Hanya student yang dapat mengakses endpoint ini")
        return view_func(request, *args, **kwargs)

    return wrapper


def check_course_owner(course, user):
    """
    Ownership validation: pastikan `user` adalah instructor pemilik `course`.
    Superuser selalu boleh lewat (override), dipakai untuk PATCH /courses/{id}.
    """
    if course.instructor_id != user.id and not user.is_superuser:
        raise HttpError(403, "Anda bukan pemilik course ini")