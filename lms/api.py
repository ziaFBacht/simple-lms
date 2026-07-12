"""
Simple LMS REST API (Django Ninja) — Updated with Redis cache, MongoDB logging,
Celery tasks, Rate Limiting, dan Report endpoint.
"""
import math
from typing import List

from django.contrib.auth import authenticate
from django.db import IntegrityError
from ninja import NinjaAPI, Router
from ninja.errors import HttpError

from lms.auth import create_access_token, decode_token, generate_tokens, jwt_auth
from lms.cache import (
    get_cached_course_detail,
    get_cached_course_list,
    invalidate_course_cache,
    rate_limit,
    set_cached_course_detail,
    set_cached_course_list,
)
from django.db.models import Avg, Count

from lms.helpers import get_object_or_404
from lms.models import Category, Course, Enrollment, Lesson, Progress, Review, Section, User, Wishlist
from lms.permissions import check_course_owner, is_admin, is_instructor, is_student
from lms.schemas import (
    CourseDetailOut,
    CourseIn,
    CourseOut,
    CourseUpdateIn,
    EnrollmentIn,
    EnrollmentOut,
    LessonIn,
    LessonOut,
    LessonUpdateIn,
    LoginIn,
    MyCourseOut,
    PaginatedCoursesOut,
    ProgressIn,
    ProgressOut,
    RefreshIn,
    RefreshOut,
    RegisterIn,
    ReviewIn,
    ReviewOut,
    SectionIn,
    SectionOut,
    StudentDashboardOut,
    TokenOut,
    UserOut,
    UserUpdateIn,
    WishlistOut,
)


# ============================================================
# AUTH ROUTER  ->  /api/auth/...
# ============================================================
auth_router = Router(tags=["Authentication"])


@auth_router.post("/register", response={201: UserOut})
def register(request, data: RegisterIn):
    """
    Registrasi user baru. Role hanya boleh 'student' atau 'instructor'.
    """
    if data.role not in ("student", "instructor"):
        raise HttpError(400, "Role hanya boleh 'student' atau 'instructor'")
    if User.objects.filter(username=data.username).exists():
        raise HttpError(400, "Username sudah digunakan")

    user = User.objects.create_user(
        username=data.username,
        email=data.email,
        password=data.password,
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
    )

    # Log activity ke MongoDB (fire-and-forget, tidak blocking)
    try:
        from lms.mongo import log_activity
        log_activity(
            user_id=user.id,
            username=user.username,
            action="register",
            detail={"role": user.role},
            ip=request.META.get("REMOTE_ADDR", ""),
        )
    except Exception:
        pass

    return 201, user


@auth_router.post("/login", response=TokenOut)
def login(request, data: LoginIn):
    """Login dan dapatkan pasangan access + refresh token (JWT)."""
    user = authenticate(request, username=data.username, password=data.password)
    if user is None:
        raise HttpError(401, "Username atau password salah")

    try:
        from lms.mongo import log_activity
        log_activity(
            user_id=user.id,
            username=user.username,
            action="login",
            ip=request.META.get("REMOTE_ADDR", ""),
        )
    except Exception:
        pass

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


# ============================================================
# COURSES ROUTER  ->  /api/courses/...
# ============================================================
courses_router = Router(tags=["Courses"])


@courses_router.get("", response=PaginatedCoursesOut)
@rate_limit
def list_courses(
    request,
    search: str = None,
    category_id: int = None,
    instructor_id: int = None,
    level: str = None,
    status: str = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 10,
):
    """
    List semua course (PUBLIC) dengan pagination, filter (search, category,
    instructor, level, status), sorting (newest/popular/rating), dan Redis caching.

    Flow:
    1. Cek Redis cache → kalau HIT, kembalikan dari cache (tidak query DB)
    2. Kalau MISS → query PostgreSQL → simpan ke Redis → kembalikan

    Rate limit: 60 request/menit per IP.
    """
    page      = max(page, 1)
    page_size = max(min(page_size, 100), 1)

    # --- Cache lookup ---
    cached = get_cached_course_list(
        page, page_size, search, category_id, instructor_id, level, status, sort
    )
    if cached:
        return cached

    # --- Cache miss: query DB ---
    qs = Course.objects.for_listing()
    if search:
        qs = qs.filter(title__icontains=search)
    if category_id:
        qs = qs.filter(category_id=category_id)
    if instructor_id:
        qs = qs.filter(instructor_id=instructor_id)
    if level:
        qs = qs.filter(level=level)
    if status:
        qs = qs.filter(status=status)

    # Annotate rating & popularity supaya bisa dipakai untuk sorting dan ditampilkan di response
    qs = qs.annotate(
        avg_rating=Avg("reviews__rating"),
        review_count=Count("reviews", distinct=True),
        enrollment_count=Count("enrollment", distinct=True),
    )

    sort_map = {
        "newest": "-id",
        "popular": "-enrollment_count",
        "rating": "-avg_rating",
    }
    qs = qs.order_by(sort_map.get(sort, "-id"))

    total = qs.count()
    pages = max(math.ceil(total / page_size), 1)
    start = (page - 1) * page_size
    items = list(qs[start: start + page_size])

    # Serialize dulu ke dict pakai schema (supaya bisa disimpan ke Redis)
    items_data = []
    for c in items:
        data = CourseOut.from_orm(c).dict()
        data["avg_rating"] = round(c.avg_rating, 2) if c.avg_rating is not None else None
        data["review_count"] = c.review_count
        items_data.append(data)

    result = {
        "items": items_data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }

    set_cached_course_list(
        result, page, page_size, search, category_id, instructor_id, level, status, sort
    )
    return result


@courses_router.get("/{course_id}", response=CourseDetailOut)
@rate_limit
def get_course(request, course_id: int):
    """
    Detail course (PUBLIC) beserta daftar lesson.

    Flow: Redis cache → DB jika miss → simpan ke Redis.
    """
    cached = get_cached_course_detail(course_id)
    if cached:
        return cached

    course = (
        Course.objects.select_related("instructor", "category")
        .prefetch_related("lessons")
        .filter(pk=course_id)
        .first()
    )
    if course is None:
        raise HttpError(404, "Course tidak ditemukan")

    data = CourseDetailOut.from_orm(course).dict()
    set_cached_course_detail(data, course_id)
    return data


@courses_router.post("", response={201: CourseOut}, auth=jwt_auth)
@is_instructor
def create_course(request, data: CourseIn):
    """
    Buat course baru (instructor only).
    Setelah create: invalidate course list cache supaya list selalu fresh.
    """
    if data.category_id is not None:
        if not Category.objects.filter(pk=data.category_id).exists():
            raise HttpError(400, f"Category dengan id={data.category_id} tidak ditemukan")

    course = Course.objects.create(
        title=data.title,
        description=data.description,
        instructor=request.auth,
        category_id=data.category_id,
    )

    # Invalidate cache
    invalidate_course_cache(course.id)

    # Log MongoDB
    try:
        from lms.mongo import log_activity
        log_activity(
            user_id=request.auth.id,
            username=request.auth.username,
            action="create_course",
            detail={"course_id": course.id, "title": course.title},
            ip=request.META.get("REMOTE_ADDR", ""),
        )
    except Exception:
        pass

    return 201, course


@courses_router.patch("/{course_id}", response=CourseOut, auth=jwt_auth)
def update_course(request, course_id: int, data: CourseUpdateIn):
    """Update sebagian data course (owner only). Invalidate cache setelah update."""
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
    invalidate_course_cache(course_id)
    return course


@courses_router.delete("/{course_id}", response={204: None}, auth=jwt_auth)
@is_admin
def delete_course(request, course_id: int):
    """Hapus course (admin only). Invalidate cache."""
    course = get_object_or_404(Course, pk=course_id)
    course.delete()
    invalidate_course_cache(course_id)
    return 204, None


# ============================================================
# ENROLLMENTS ROUTER  ->  /api/enrollments/...
# ============================================================
enrollments_router = Router(tags=["Enrollments"])


@enrollments_router.post("", response={201: EnrollmentOut}, auth=jwt_auth)
@is_student
def enroll_course(request, data: EnrollmentIn):
    """
    Mendaftar ke course (student only).
    Setelah berhasil → trigger Celery task send_enrollment_email (async).
    """
    course = get_object_or_404(Course, pk=data.course_id)

    from django.db import transaction
    try:
        with transaction.atomic():
            enrollment = Enrollment.objects.create(student=request.auth, course=course)
    except IntegrityError:
        raise HttpError(409, "Anda sudah terdaftar di course ini")

    # Trigger email async via Celery (tidak blocking response)
    try:
        from lms.tasks import send_enrollment_email
        send_enrollment_email.delay(request.auth.id, course.id)
    except Exception as e:
        # Kalau Celery broker mati, endpoint tetap berhasil (email tidak kritis)
        print(f"[CELERY WARNING] send_enrollment_email.delay failed: {e}")

    # Log MongoDB
    try:
        from lms.mongo import log_activity
        log_activity(
            user_id=request.auth.id,
            username=request.auth.username,
            action="enroll",
            detail={"course_id": course.id, "course_title": course.title},
            ip=request.META.get("REMOTE_ADDR", ""),
        )
    except Exception:
        pass

    return 201, enrollment


@enrollments_router.get("/my-courses", response=List[MyCourseOut], auth=jwt_auth)
def my_courses(request):
    """Daftar course yang sudah diikuti user yang sedang login, beserta progress."""
    enrollments = (
        Enrollment.objects.filter(student=request.auth)
        .for_student_dashboard()
        .order_by("-enrolled_at")
    )

    result = []
    for enrollment in enrollments:
        lessons_total     = enrollment.course.lessons.count()
        lessons_completed = Progress.objects.filter(
            student=request.auth, lesson__course=enrollment.course, completed=True
        ).count()
        percentage = (
            round((lessons_completed / lessons_total) * 100, 2) if lessons_total else 0.0
        )
        result.append({
            "enrollment_id":    enrollment.id,
            "course":           enrollment.course,
            "enrolled_at":      enrollment.enrolled_at,
            "lessons_total":    lessons_total,
            "lessons_completed":lessons_completed,
            "progress_percentage": percentage,
        })

    return result


@enrollments_router.post("/{enrollment_id}/progress", response=ProgressOut, auth=jwt_auth)
def mark_progress(request, enrollment_id: int, data: ProgressIn):
    """
    Tandai lesson selesai/belum.
    Jika progress mencapai 100% → trigger Celery task generate_certificate (async).
    """
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)

    if enrollment.student_id != request.auth.id:
        raise HttpError(403, "Ini bukan enrollment milik Anda")

    lesson = get_object_or_404(Lesson, pk=data.lesson_id)
    if lesson.course_id != enrollment.course_id:
        raise HttpError(400, "Lesson ini bukan bagian dari course yang Anda ikuti")

    progress, _created = Progress.objects.update_or_create(
        student=request.auth,
        lesson=lesson,
        defaults={"completed": data.completed},
    )

    # Cek apakah semua lesson sudah selesai → trigger certificate
    if data.completed:
        total_lessons = Lesson.objects.filter(course=enrollment.course).count()
        completed_count = Progress.objects.filter(
            student=request.auth,
            lesson__course=enrollment.course,
            completed=True,
        ).count()
        if total_lessons > 0 and completed_count >= total_lessons:
            try:
                from lms.tasks import generate_certificate
                generate_certificate.delay(request.auth.id, enrollment.course_id)
            except Exception as e:
                print(f"[CELERY WARNING] generate_certificate.delay failed: {e}")

    # Log MongoDB
    try:
        from lms.mongo import log_activity
        log_activity(
            user_id=request.auth.id,
            username=request.auth.username,
            action="mark_progress",
            detail={
                "lesson_id": lesson.id,
                "lesson_title": lesson.title,
                "completed": data.completed,
            },
            ip=request.META.get("REMOTE_ADDR", ""),
        )
    except Exception:
        pass

    return progress


# ============================================================
# REPORTS ROUTER  ->  /api/reports/...
# ============================================================
reports_router = Router(tags=["Reports"])


@reports_router.get("/courses/{course_id}/export", auth=jwt_auth)
@is_admin
def export_report(request, course_id: int):
    """
    Trigger async CSV export untuk satu course.
    Task berjalan di Celery worker; response langsung mengembalikan task ID.
    """
    course = get_object_or_404(Course, pk=course_id)
    from lms.tasks import export_course_report
    task = export_course_report.delay(course_id, request.auth.id)
    return {
        "message": "Export sedang diproses di background",
        "task_id": task.id,
        "course":  course.title,
    }


@reports_router.get("/analytics/top-courses", auth=jwt_auth)
@is_admin
def top_courses_report(request, limit: int = 5):
    """Top N course berdasarkan jumlah student (dari MongoDB analytics)."""
    from lms.mongo import aggregate_top_courses
    return aggregate_top_courses(limit=limit)


@reports_router.get("/analytics/activity-summary", auth=jwt_auth)
@is_admin
def activity_summary_report(request, days: int = 7):
    """Ringkasan aktivitas dalam N hari terakhir (dari MongoDB activity logs)."""
    from lms.mongo import aggregate_activity_summary
    return aggregate_activity_summary(days=days)


@reports_router.get("/courses/{course_id}/analytics", auth=jwt_auth)
@is_admin
def course_analytics(request, course_id: int):
    """Detail analytics satu course dari MongoDB."""
    from lms.mongo import get_course_analytics
    data = get_course_analytics(course_id)
    if not data:
        raise HttpError(404, "Analytics untuk course ini belum tersedia. Jalankan update_course_statistics task.")
    return data


# ============================================================
# LESSONS ROUTER  ->  /api/lessons/...
# ============================================================
lessons_router = Router(tags=["Lessons"])


@courses_router.post("/{course_id}/lessons", response={201: LessonOut}, auth=jwt_auth)
@is_instructor
def create_lesson(request, course_id: int, data: LessonIn):
    """Buat lesson baru dalam course (owner only)."""
    course = get_object_or_404(Course, pk=course_id)
    check_course_owner(course, request.auth)
    lesson = Lesson.objects.create(
        course=course,
        title=data.title,
        content=data.content,
        order=data.order,
    )
    # Invalidate cache detail course
    invalidate_course_cache(course.id)
    return 201, lesson


@courses_router.get("/{course_id}/lessons", response=List[LessonOut])
def list_lessons(request, course_id: int):
    """Daftar lesson dalam course (PUBLIC)."""
    course = get_object_or_404(Course, pk=course_id)
    return list(course.lessons.all())


@lessons_router.get("/{lesson_id}", response=LessonOut)
def get_lesson(request, lesson_id: int):
    """Detail lesson (PUBLIC)."""
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    return lesson


@lessons_router.patch("/{lesson_id}", response=LessonOut, auth=jwt_auth)
def update_lesson(request, lesson_id: int, data: LessonUpdateIn):
    """Update lesson (owner only)."""
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    check_course_owner(lesson.course, request.auth)

    if data.title is not None:
        lesson.title = data.title
    if data.content is not None:
        lesson.content = data.content
    if data.order is not None:
        lesson.order = data.order

    lesson.save()
    invalidate_course_cache(lesson.course.id)
    return lesson


@lessons_router.delete("/{lesson_id}", response={204: None}, auth=jwt_auth)
def delete_lesson(request, lesson_id: int):
    """Hapus lesson (owner/admin only)."""
    lesson = get_object_or_404(Lesson, pk=lesson_id)
    if request.auth.role != "admin":
        check_course_owner(lesson.course, request.auth)

    course_id = lesson.course.id
    lesson.delete()
    invalidate_course_cache(course_id)
    return 204, None


# ============================================================
# CURRICULUM (SECTIONS) -> /api/courses/{id}/sections, /api/courses/{id}/curriculum
# ============================================================
@courses_router.post("/{course_id}/sections", response={201: SectionOut}, auth=jwt_auth)
@is_instructor
def create_section(request, course_id: int, data: SectionIn):
    """Buat section baru dalam course (owner only). Dipakai untuk menyusun curriculum."""
    course = get_object_or_404(Course, pk=course_id)
    check_course_owner(course, request.auth)

    section = Section.objects.create(course=course, title=data.title, order=data.order)
    invalidate_course_cache(course.id)
    return 201, section


@courses_router.get("/{course_id}/curriculum", response=List[SectionOut])
def get_curriculum(request, course_id: int):
    """
    Curriculum lengkap course (PUBLIC): daftar section beserta lesson di dalamnya,
    terurut sesuai field `order`.
    """
    course = get_object_or_404(Course, pk=course_id)
    return list(course.sections.prefetch_related("lessons").all())


# ============================================================
# REVIEWS -> /api/courses/{id}/reviews
# ============================================================
@courses_router.post("/{course_id}/reviews", response={201: ReviewOut}, auth=jwt_auth)
@is_student
def create_or_update_review(request, course_id: int, data: ReviewIn):
    """
    Buat atau update review untuk course (student yang sudah enroll saja).
    Satu student hanya bisa punya satu review per course — submit kedua akan
    meng-update review yang sudah ada (bukan membuat baris baru).
    """
    course = get_object_or_404(Course, pk=course_id)

    if not Enrollment.objects.filter(student=request.auth, course=course).exists():
        raise HttpError(403, "Anda harus enroll di course ini sebelum memberi review")

    if not (1 <= data.rating <= 5):
        raise HttpError(400, "Rating harus antara 1 sampai 5")

    review, _created = Review.objects.update_or_create(
        student=request.auth,
        course=course,
        defaults={"rating": data.rating, "comment": data.comment},
    )

    # Rating berubah -> avg_rating pada cache course list/detail jadi basi
    invalidate_course_cache(course.id)

    return 201, review


@courses_router.get("/{course_id}/reviews", response=List[ReviewOut])
def list_reviews(request, course_id: int):
    """Daftar review untuk sebuah course (PUBLIC)."""
    course = get_object_or_404(Course, pk=course_id)
    return list(course.reviews.select_related("student").order_by("-created_at"))


# ============================================================
# WISHLIST ROUTER  ->  /api/wishlist/...
# ============================================================
wishlist_router = Router(tags=["Wishlist"])


@wishlist_router.post("/{course_id}", response={201: WishlistOut}, auth=jwt_auth)
@is_student
def add_wishlist(request, course_id: int):
    """Tambahkan course ke wishlist student yang sedang login."""
    course = get_object_or_404(Course, pk=course_id)
    wishlist, created = Wishlist.objects.get_or_create(student=request.auth, course=course)
    if not created:
        raise HttpError(400, "Course ini sudah ada di wishlist Anda")
    return 201, wishlist


@wishlist_router.delete("/{course_id}", response={204: None}, auth=jwt_auth)
@is_student
def remove_wishlist(request, course_id: int):
    """Hapus course dari wishlist student yang sedang login."""
    deleted, _ = Wishlist.objects.filter(student=request.auth, course_id=course_id).delete()
    if not deleted:
        raise HttpError(404, "Course ini tidak ada di wishlist Anda")
    return 204, None


@wishlist_router.get("", response=List[WishlistOut], auth=jwt_auth)
@is_student
def my_wishlist(request):
    """Daftar course yang di-wishlist oleh student yang sedang login."""
    return list(
        Wishlist.objects.filter(student=request.auth)
        .select_related("course")
        .order_by("-created_at")
    )


# ============================================================
# STUDENTS ROUTER  ->  /api/students/...
# ============================================================
students_router = Router(tags=["Students"])


@students_router.get("/me/dashboard", response=StudentDashboardOut, auth=jwt_auth)
@is_student
def student_dashboard(request):
    """
    Dashboard ringkas untuk student yang sedang login:
    - Course aktif (progress belum 100%) beserta persentase progress.
    - Course yang sudah selesai (progress 100%).
    - Jumlah course di wishlist.
    - Total course yang pernah di-enroll.
    - Rekomendasi course: diambil dari category yang sama dengan course yang
      sudah di-enroll, belum pernah di-enroll, status published, diurutkan
      berdasarkan rating tertinggi.
    """
    enrollments = (
        Enrollment.objects.filter(student=request.auth)
        .for_student_dashboard()
        .order_by("-enrolled_at")
    )

    active_courses = []
    completed_courses = []
    enrolled_category_ids = set()
    enrolled_course_ids = []

    for enrollment in enrollments:
        enrolled_course_ids.append(enrollment.course_id)
        if enrollment.course.category_id:
            enrolled_category_ids.add(enrollment.course.category_id)

        lessons_total = enrollment.course.lessons.count()
        lessons_completed = Progress.objects.filter(
            student=request.auth, lesson__course=enrollment.course, completed=True
        ).count()
        percentage = (
            round((lessons_completed / lessons_total) * 100, 2) if lessons_total else 0.0
        )

        item = {
            "enrollment_id": enrollment.id,
            "course": enrollment.course,
            "enrolled_at": enrollment.enrolled_at,
            "lessons_total": lessons_total,
            "lessons_completed": lessons_completed,
            "progress_percentage": percentage,
        }

        # Course dianggap "selesai" hanya kalau punya lesson DAN semuanya sudah completed.
        # Course tanpa lesson sama sekali tetap dianggap "aktif" (belum ada progress untuk dinilai).
        if lessons_total > 0 and lessons_completed >= lessons_total:
            completed_courses.append(item)
        else:
            active_courses.append(item)

    wishlist_count = Wishlist.objects.filter(student=request.auth).count()

    recommended_qs = (
        Course.objects.for_listing()
        .filter(category_id__in=enrolled_category_ids, status="published")
        .exclude(id__in=enrolled_course_ids)
        .annotate(avg_rating=Avg("reviews__rating"), review_count=Count("reviews", distinct=True))
        .order_by("-avg_rating", "-id")[:5]
    )
    recommended_courses = []
    for c in recommended_qs:
        data = CourseOut.from_orm(c).dict()
        data["avg_rating"] = round(c.avg_rating, 2) if c.avg_rating is not None else None
        data["review_count"] = c.review_count
        recommended_courses.append(data)

    return {
        "active_courses": active_courses,
        "completed_courses": completed_courses,
        "wishlist_count": wishlist_count,
        "total_courses_enrolled": len(enrolled_course_ids),
        "recommended_courses": recommended_courses,
    }


# ============================================================
# MAIN NinjaAPI INSTANCE
# ============================================================
api = NinjaAPI(
    title="Simple LMS API",
    version="2.0.0",
    description=(
        "REST API untuk Simple LMS — Django Ninja + JWT + Redis Cache "
        "+ MongoDB Analytics + Celery Tasks."
    ),
    docs_url="/docs",
)

api.add_router("/auth",        auth_router)
api.add_router("/courses",     courses_router)
api.add_router("/lessons",     lessons_router)
api.add_router("/enrollments", enrollments_router)
api.add_router("/reports",     reports_router)
api.add_router("/wishlist",    wishlist_router)
api.add_router("/students",    students_router)