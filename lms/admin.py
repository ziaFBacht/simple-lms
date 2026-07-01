from django.contrib import admin

from lms.models import (
    Category,
    Course,
    Enrollment,
    Lesson,
    Progress,
    Review,
    Section,
    User,
    Wishlist,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "role", "is_staff", "is_superuser")
    list_filter = ("role",)
    search_fields = ("username", "email")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "parent")
    search_fields = ("name",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "instructor", "category", "level", "status")
    list_filter = ("level", "status", "category")
    search_fields = ("title", "description")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "course", "order")
    list_filter = ("course",)
    ordering = ("course", "order")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "course", "section", "order")
    list_filter = ("course",)
    ordering = ("course", "order")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "course", "enrolled_at")
    list_filter = ("course",)


@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "lesson", "completed")
    list_filter = ("completed",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "course", "rating", "created_at")
    list_filter = ("rating",)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "course", "created_at")