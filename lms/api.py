"""
Simple LMS REST API (Django Ninja).
"""
import math
from typing import List

from django.contrib.auth import authenticate
from django.db import IntegrityError
from ninja import NinjaAPI, Router
from ninja.errors import HttpError

from lms.auth import create_access_token, decode_token, generate_tokens, jwt_auth
from lms.helpers import get_object_or_404
from lms.models import Course, Enrollment, Lesson, Progress, User
from lms.permissions import check_course_owner, is_admin, is_instructor, is_student
from lms.schemas import (
    CourseDetailOut, CourseIn, CourseOut, CourseUpdateIn,
    EnrollmentIn, EnrollmentOut, LoginIn, MyCourseOut, PaginatedCoursesOut,
    ProgressIn, ProgressOut, RefreshIn, RefreshOut, RegisterIn, TokenOut,
    UserOut, UserUpdateIn,
)
from lms.models import Category, Course, Enrollment, Lesson, Progress, User  # tambah Category

auth_router = Router(tags=["Authentication"])


@auth_router.post("/register", response={201: UserOut})
def register(request, data: RegisterIn):
    """Registrasi user baru. Role hanya boleh 'student' atau 'instructor'."""
    if data.role not in ("student", "instructor"):
        raise HttpError(400, "Role hanya boleh 'student' atau 'instructor'")

    if User.objects.filter(username=data.username).exists():
        raise HttpError(400, "Username sudah digunakan")

    if User.objects.filter(email=data.email).exists():
        raise HttpError(400, "Email sudah digunakan")

    # create_user() otomatis melakukan hashing password (PBKDF2 + SHA256)
    user = User.objects.create_user(
        username=data.username,
        email=data.email,
        password=data.password,
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
    )
    return 201, user


@auth_router.post("/login", response=TokenOut)
def login(request, data: LoginIn):
    """Login dan dapatkan pasangan access + refresh token (JWT)."""
    user = authenticate(request, username=data.username, password=data.password)
    if user is None:
        raise HttpError(401, "Username atau password salah")
    return generate_tokens(user)


@auth_router.post("/refresh", response=RefreshOut)
def refresh_token(request, data: RefreshIn):
    """Tukar refresh token yang masih valid dengan access token baru."""
    payload = decode_token(data.refresh)

    if payload.get("token_type") != "refresh":
        raise HttpError(401, "Token ini bukan refresh token yang valid")

    user = get_object_or_404(User, pk=payload["user_id"])
    return {"access": create_access_token(user), "token_type": "bearer"}


@auth_router.get("/me", response=UserOut, auth=jwt_auth)
def get_me(request):
    """Ambil data profile user yang sedang login."""
    return request.auth


@auth_router.put("/me", response=UserOut, auth=jwt_auth)
def update_me(request, data: UserUpdateIn):
    """Update profile user yang sedang login (field opsional)."""
    user = request.auth

    if data.email is not None and data.email != user.email:
        if User.objects.filter(email=data.email).exclude(pk=user.pk).exists():
            raise HttpError(400, "Email sudah digunakan oleh user lain")
        user.email = data.email

    if data.first_name is not None:
        user.first_name = data.first_name
    if data.last_name is not None:
        user.last_name = data.last_name

    user.save()
    return user

courses_router = Router(tags=["Courses"])


@courses_router.get("", response=PaginatedCoursesOut)
def list_courses(
    request,
    search: str = None,
    category_id: int = None,
    instructor_id: int = None,
    page: int = 1,
    page_size: int = 10,
):
    """
    List semua course (PUBLIC) dengan pagination & filter opsional.

    Query params:
    - search: cari berdasarkan judul course
    - category_id / instructor_id: filter
    - page, page_size: pagination
    """
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)

    qs = Course.objects.for_listing()  # select_related('instructor', 'category')
    if search:
        qs = qs.filter(title__icontains=search)
    if category_id:
        qs = qs.filter(category_id=category_id)
    if instructor_id:
        qs = qs.filter(instructor_id=instructor_id)

    total = qs.count()
    pages = max(math.ceil(total / page_size), 1)
    start = (page - 1) * page_size
    items = list(qs.order_by("id")[start : start + page_size])

    return {
        "items": items, "total": total,
        "page": page, "page_size": page_size, "pages": pages,
    }


@courses_router.get("/{course_id}", response=CourseDetailOut)
def get_course(request, course_id: int):
    """Detail course (PUBLIC) beserta daftar lesson di dalamnya."""
    course = (
        Course.objects.select_related("instructor", "category")
        .prefetch_related("lessons")
        .filter(pk=course_id)
        .first()
    )
    if course is None:
        raise HttpError(404, "Course tidak ditemukan")
    return course


@courses_router.post("", response={201: CourseOut}, auth=jwt_auth)
@is_instructor
def create_course(request, data: CourseIn):
    """Buat course baru. Hanya untuk user dengan role='instructor'."""
    if data.category_id is not None:
        if not Category.objects.filter(pk=data.category_id).exists():
            raise HttpError(400, f"Category dengan id={data.category_id} tidak ditemukan")

    course = Course.objects.create(
        title=data.title,
        description=data.description,
        instructor=request.auth,
        category_id=data.category_id,
    )
    return 201, course


@courses_router.patch("/{course_id}", response=CourseOut, auth=jwt_auth)
def update_course(request, course_id: int, data: CourseUpdateIn):
    """Update sebagian data course. Hanya untuk instructor pemilik course."""
    course = get_object_or_404(Course, pk=course_id)
    check_course_owner(course, request.auth)

    if data.category_id is not None:
        if not Category.objects.filter(pk=data.category_id).exists():
            raise HttpError(400, f"Category dengan id={data.category_id} tidak ditemukan")

    if data.title is not None:
        course.title = data.title
    if data.description is not None:
        course.description = data.description
    if data.category_id is not None:
        course.category_id = data.category_id

    course.save()
    return course


@courses_router.delete("/{course_id}", response={204: None}, auth=jwt_auth)
@is_admin
def delete_course(request, course_id: int):
    """Hapus course. Hanya untuk role='admin'."""
    course = get_object_or_404(Course, pk=course_id)
    course.delete()
    return 204, None

enrollments_router = Router(tags=["Enrollments"])


@enrollments_router.post("", response={201: EnrollmentOut}, auth=jwt_auth)
@is_student
def enroll_course(request, data: EnrollmentIn):
    """Mendaftar (enroll) ke sebuah course. Hanya untuk role='student'."""
    course = get_object_or_404(Course, pk=data.course_id)

    try:
        enrollment = Enrollment.objects.create(student=request.auth, course=course)
    except IntegrityError:
        raise HttpError(409, "Anda sudah terdaftar di course ini")

    return 201, enrollment


@enrollments_router.get("/my-courses", response=List[MyCourseOut], auth=jwt_auth)
def my_courses(request):
    """Daftar course yang sudah diikuti oleh user yang sedang login, beserta progress."""
    enrollments = Enrollment.objects.filter(
        student=request.auth
    ).for_student_dashboard().order_by("-enrolled_at")

    result = []
    for enrollment in enrollments:
        lessons_total = enrollment.course.lessons.count()
        lessons_completed = Progress.objects.filter(
            student=request.auth, lesson__course=enrollment.course, completed=True
        ).count()
        percentage = (
            round((lessons_completed / lessons_total) * 100, 2) if lessons_total else 0.0
        )

        result.append({
            "enrollment_id": enrollment.id,
            "course": enrollment.course,
            "enrolled_at": enrollment.enrolled_at,
            "lessons_total": lessons_total,
            "lessons_completed": lessons_completed,
            "progress_percentage": percentage,
        })

    return result


@enrollments_router.post("/{enrollment_id}/progress", response=ProgressOut, auth=jwt_auth)
def mark_progress(request, enrollment_id: int, data: ProgressIn):
    """Tandai sebuah lesson sebagai selesai/belum, dalam konteks enrollment tertentu."""
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)

    # Ownership validation: hanya pemilik enrollment yang boleh update progress-nya
    if enrollment.student_id != request.auth.id:
        raise HttpError(403, "Ini bukan enrollment milik Anda")

    lesson = get_object_or_404(Lesson, pk=data.lesson_id)
    if lesson.course_id != enrollment.course_id:
        raise HttpError(400, "Lesson ini bukan bagian dari course yang Anda ikuti")

    progress, _created = Progress.objects.update_or_create(
        student=request.auth, lesson=lesson,
        defaults={"completed": data.completed},
    )
    return progress

api = NinjaAPI(
    title="Simple LMS API",
    version="1.0.0",
    description="REST API untuk Simple Learning Management System (Django Ninja + JWT).",
    docs_url="/docs",
)

api.add_router("/auth", auth_router)
api.add_router("/courses", courses_router)
api.add_router("/enrollments", enrollments_router)