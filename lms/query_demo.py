from django.db import connection, reset_queries
from lms.models import Course, Enrollment


def print_queries(label):
    print(f"\n=== {label} ===")
    print(f"Total queries: {len(connection.queries)}")


def naive_courses():
    reset_queries()
    courses = Course.objects.all()

    for c in courses:
        # akan trigger query tambahan tiap loop (N+1)
        print(c.title, "-", c.instructor.username)

    print_queries("NAIVE COURSES")


def optimized_courses():
    reset_queries()
    courses = Course.objects.select_related('instructor')

    for c in courses:
        print(c.title, "-", c.instructor.username)

    print_queries("OPTIMIZED COURSES")


def naive_enrollments():
    reset_queries()
    enrollments = Enrollment.objects.all()

    for e in enrollments:
        print(e.student.username, "-", e.course.title)

    print_queries("NAIVE ENROLLMENTS")


def optimized_enrollments():
    reset_queries()
    enrollments = Enrollment.objects.select_related('student', 'course')

    for e in enrollments:
        print(e.student.username, "-", e.course.title)

    print_queries("OPTIMIZED ENROLLMENTS")