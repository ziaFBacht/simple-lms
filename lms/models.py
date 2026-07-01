from django.db import models
from django.contrib.auth.models import AbstractUser


# ======================
# USER (Custom User)
# ======================
class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('instructor', 'Instructor'),
        ('student', 'Student'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)


# ======================
# CATEGORY (Hierarchy)
# ======================
class Category(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )

    def __str__(self):
        return self.name


# ======================
# COURSE
# ======================
class CourseQuerySet(models.QuerySet):
    def for_listing(self):
        return self.select_related('instructor', 'category')


class Course(models.Model):
    LEVEL_CHOICES = (
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    )
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    )

    title = models.CharField(max_length=200)
    description = models.TextField()
    instructor = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='beginner')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='published')

    objects = CourseQuerySet.as_manager()

    def __str__(self):
        return self.title


# ======================
# SECTION (Curriculum grouping for lessons)
# ======================
class Section(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title


# ======================
# LESSON (Ordering)
# ======================
class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons')
    section = models.ForeignKey(
        Section, on_delete=models.CASCADE, related_name='lessons',
        null=True, blank=True
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title


# ======================
# ENROLLMENT (Unique)
# ======================
class EnrollmentQuerySet(models.QuerySet):
    def for_student_dashboard(self):
        return self.select_related('course').prefetch_related('course__lessons')


class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    objects = EnrollmentQuerySet.as_manager()

    class Meta:
        unique_together = ('student', 'course')


# ======================
# PROGRESS
# ======================
class Progress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student', 'lesson')


# ======================
# REVIEW (Rating + comment, 1 per student per course)
# ======================
class Review(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField()  # divalidasi 1-5 di schema/endpoint, bukan di sini
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student.username} -> {self.course.title} ({self.rating})"


# ======================
# WISHLIST (Bookmarked courses per student)
# ======================
class Wishlist(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlists')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='wishlists')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student.username} wishlisted {self.course.title}"