"""
Pydantic Schemas (Django Ninja `Schema`) untuk Simple LMS API.
"""
from datetime import datetime
from typing import List, Optional

from ninja import Schema


# ============================================================
# AUTH SCHEMAS
# ============================================================
class RegisterIn(Schema):
    """Input untuk registrasi user baru."""
    username: str
    email: str
    password: str
    first_name: str = ""
    last_name: str = ""
    # Hanya boleh 'student' atau 'instructor'. Role 'admin' tidak boleh
    # didaftarkan lewat endpoint publik, harus dibuat lewat Django admin.
    role: str = "student"


class UserOut(Schema):
    """Representasi user yang aman untuk dikembalikan ke client (tanpa password)."""
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    role: str


class UserUpdateIn(Schema):
    """Input untuk update profile (PUT /api/auth/me). Semua field opsional."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None


class LoginIn(Schema):
    username: str
    password: str


class TokenOut(Schema):
    access: str
    refresh: str
    token_type: str = "bearer"


class RefreshIn(Schema):
    refresh: str


class RefreshOut(Schema):
    access: str
    token_type: str = "bearer"


# ============================================================
# CATEGORY / COURSE / LESSON SCHEMAS
# ============================================================
class CategoryOut(Schema):
    id: int
    name: str
    parent_id: Optional[int] = None


class LessonOut(Schema):
    id: int
    title: str
    content: str
    order: int


class LessonIn(Schema):
    """Input untuk membuat lesson baru."""
    title: str
    content: str
    order: int


class LessonUpdateIn(Schema):
    """Input untuk memperbarui lesson (semua field opsional)."""
    title: Optional[str] = None
    content: Optional[str] = None
    order: Optional[int] = None


class CourseIn(Schema):
    """Input untuk membuat course baru (POST /api/courses)."""
    title: str
    description: str
    category_id: Optional[int] = None


class CourseUpdateIn(Schema):
    """Input untuk update sebagian data course (PATCH /api/courses/{id})."""
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None


class CourseOut(Schema):
    """Output ringkas Course, dipakai pada list & nested response."""
    id: int
    title: str
    description: str
    instructor: UserOut
    category: Optional[CategoryOut] = None
    level: str = "beginner"
    status: str = "published"
    avg_rating: Optional[float] = None
    review_count: int = 0


class CourseDetailOut(CourseOut):
    """Output detail Course, termasuk daftar lesson di dalamnya."""
    lessons: List[LessonOut] = []

    @staticmethod
    def resolve_lessons(obj):
        return obj.lessons.all()


class PaginatedCoursesOut(Schema):
    """Wrapper pagination untuk GET /api/courses."""
    items: List[CourseOut]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================
# ENROLLMENT / PROGRESS SCHEMAS
# ============================================================
class EnrollmentIn(Schema):
    course_id: int


class EnrollmentOut(Schema):
    id: int
    course: CourseOut
    enrolled_at: datetime


class ProgressIn(Schema):
    lesson_id: int
    completed: bool = True


class ProgressOut(Schema):
    id: int
    lesson_id: int
    completed: bool


class MyCourseOut(Schema):
    """Output untuk GET /api/enrollments/my-courses."""
    enrollment_id: int
    course: CourseOut
    enrolled_at: datetime
    lessons_total: int
    lessons_completed: int
    progress_percentage: float


# ============================================================
# SECTION / CURRICULUM SCHEMAS
# ============================================================
class SectionIn(Schema):
    """Input untuk membuat section baru dalam course."""
    title: str
    order: int


class SectionOut(Schema):
    """Output Section beserta daftar lesson di dalamnya (nested curriculum)."""
    id: int
    title: str
    order: int
    lessons: List[LessonOut] = []

    @staticmethod
    def resolve_lessons(obj):
        return obj.lessons.all()


# ============================================================
# REVIEW SCHEMAS
# ============================================================
class ReviewIn(Schema):
    """Input untuk membuat/update review course. Rating divalidasi 1-5 di endpoint."""
    rating: int
    comment: Optional[str] = None


class ReviewOut(Schema):
    id: int
    student: UserOut
    rating: int
    comment: Optional[str] = None
    created_at: datetime


# ============================================================
# WISHLIST SCHEMAS
# ============================================================
class WishlistOut(Schema):
    id: int
    course: CourseOut
    created_at: datetime


# ============================================================
# STUDENT DASHBOARD SCHEMA
# ============================================================
class StudentDashboardOut(Schema):
    """Output untuk GET /api/students/me/dashboard."""
    active_courses: List[MyCourseOut] = []
    completed_courses: List[MyCourseOut] = []
    wishlist_count: int = 0
    total_courses_enrolled: int = 0
    recommended_courses: List[CourseOut] = []