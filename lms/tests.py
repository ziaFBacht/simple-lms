from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from ninja.testing import TestClient

# Semua email akan lewat email saya

from lms.api import api
from lms.models import Course, Lesson, Enrollment, Progress, Category, Section, Review, Wishlist, User
from lms.auth import create_access_token

User = get_user_model()


class SimpleLMSTestSuite(TestCase):
    def setUp(self):
        """Set up test client and create mock users."""
        self.client = TestClient(api)

        # Create instructor user
        self.instructor = User.objects.create_user(
            username="instructor_test",
            email="instructor@test.com",
            password="testpassword123",
            role="instructor"
        )
        self.instructor_token = create_access_token(self.instructor)
        self.instructor_headers = {"Authorization": f"Bearer {self.instructor_token}"}

        # Create another instructor user (non-owner)
        self.other_instructor = User.objects.create_user(
            username="instructor_other",
            email="instructor2@test.com",
            password="testpassword123",
            role="instructor"
        )
        self.other_instructor_token = create_access_token(self.other_instructor)
        self.other_instructor_headers = {"Authorization": f"Bearer {self.other_instructor_token}"}

        # Create student user
        self.student = User.objects.create_user(
            username="student_test",
            email="student@test.com",
            password="testpassword123",
            role="student"
        )
        self.student_token = create_access_token(self.student)
        self.student_headers = {"Authorization": f"Bearer {self.student_token}"}

        # Create admin user
        self.admin = User.objects.create_superuser(
            username="admin_test",
            email="admin@test.com",
            password="testpassword123",
            role="admin"
        )
        self.admin_token = create_access_token(self.admin)
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Create a category
        self.category = Category.objects.create(name="Computer Science")

    # ==========================================
    # AUTHENTICATION TESTS
    # ==========================================
    def test_register_user_success(self):
        """Test registering a new student user successfully."""
        data = {
            "username": "new_student",
            "email": "new_student@test.com",
            "password": "strongpassword123",
            "role": "student",
            "first_name": "New",
            "last_name": "Student"
        }
        response = self.client.post("/auth/register", json=data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["username"], "new_student")
        self.assertEqual(response.json()["role"], "student")

    def test_register_user_duplicate_username(self):
        """Test registering a user with an already existing username returns 400."""
        data = {
            "username": "student_test",  # Already exists
            "email": "another@test.com",
            "password": "strongpassword123",
            "role": "student"
        }
        response = self.client.post("/auth/register", json=data)
        self.assertEqual(response.status_code, 400)

    def test_register_user_duplicate_email_is_allowed(self):
        """Test registering a second, different-username account with an email
        that's already used by another account succeeds (email is not unique)."""
        first = {
            "username": "email_owner_1",
            "email": "shared@test.com",
            "password": "strongpassword123",
            "role": "student",
        }
        response = self.client.post("/auth/register", json=first)
        self.assertEqual(response.status_code, 201)

        second = {
            "username": "email_owner_2",  # different username, same email
            "email": "shared@test.com",
            "password": "strongpassword123",
            "role": "instructor",
        }
        response = self.client.post("/auth/register", json=second)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["username"], "email_owner_2")

        self.assertEqual(User.objects.filter(email="shared@test.com").count(), 2)

    def test_login_success(self):
        """Test logging in with valid credentials returns JWT tokens."""
        data = {
            "username": "student_test",
            "password": "testpassword123"
        }
        response = self.client.post("/auth/login", json=data)
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertIn("access", res_data)
        self.assertIn("refresh", res_data)
        self.assertEqual(res_data["token_type"], "bearer")

    def test_login_invalid_credentials(self):
        """Test logging in with incorrect password returns 401."""
        data = {
            "username": "student_test",
            "password": "wrongpassword"
        }
        response = self.client.post("/auth/login", json=data)
        self.assertEqual(response.status_code, 401)

    def test_get_me_authenticated(self):
        """Test fetching current user details with a valid JWT token."""
        response = self.client.get("/auth/me", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "student_test")

    def test_get_me_unauthenticated(self):
        """Test fetching current user details without credentials returns 401."""
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

    # ==========================================
    # COURSE CRUD TESTS
    # ==========================================
    def test_create_course_success_as_instructor(self):
        """Test creating a course as an instructor."""
        data = {
            "title": "Django Advanced",
            "description": "Deep dive into Django internals",
            "category_id": self.category.id
        }
        response = self.client.post("/courses", json=data, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Django Advanced")
        self.assertEqual(response.json()["instructor"]["username"], "instructor_test")

    def test_create_course_forbidden_as_student(self):
        """Test that a student is not allowed to create a course (returns 403)."""
        data = {
            "title": "Django for Students",
            "description": "Django basics"
        }
        response = self.client.post("/courses", json=data, headers=self.student_headers)
        self.assertEqual(response.status_code, 403)

    def test_list_courses_public(self):
        """Test listing courses is public and returns a paginated list."""
        # Create a course first
        Course.objects.create(
            title="Python Basic Test",
            description="Introduction to Python",
            instructor=self.instructor,
            category=self.category
        )
        response = self.client.get("/courses")
        self.assertEqual(response.status_code, 200)
        self.assertIn("items", response.json())
        self.assertGreaterEqual(response.json()["total"], 1)

    # ==========================================
    # LESSON CRUD TESTS
    # ==========================================
    def test_lesson_crud_flow(self):
        """Test create, read, update, delete operations for Lessons."""
        # 1. Setup course
        course = Course.objects.create(
            title="Lesson Test Course",
            description="Test Course for Lessons",
            instructor=self.instructor
        )

        # 2. Test create lesson (Instructor Owner) -> POST /api/courses/{id}/lessons
        lesson_data = {
            "title": "Lesson 1: Introduction",
            "content": "This is the first lesson content.",
            "order": 1
        }
        response = self.client.post(
            f"/courses/{course.id}/lessons",
            json=lesson_data,
            headers=self.instructor_headers
        )
        self.assertEqual(response.status_code, 201)
        lesson_id = response.json()["id"]
        self.assertEqual(response.json()["title"], "Lesson 1: Introduction")

        # 3. Test create lesson from non-owner instructor -> Should return 403
        response = self.client.post(
            f"/courses/{course.id}/lessons",
            json=lesson_data,
            headers=self.other_instructor_headers
        )
        self.assertEqual(response.status_code, 403)

        # 4. Test list lessons under course (Public) -> GET /api/courses/{id}/lessons
        response = self.client.get(f"/courses/{course.id}/lessons")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["title"], "Lesson 1: Introduction")

        # 5. Test get lesson detail (Public) -> GET /api/lessons/{id}
        response = self.client.get(f"/lessons/{lesson_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "This is the first lesson content.")

        # 6. Test patch lesson (Owner only) -> PATCH /api/lessons/{id}
        patch_data = {"title": "Updated Lesson Title"}
        response = self.client.patch(
            f"/lessons/{lesson_id}",
            json=patch_data,
            headers=self.instructor_headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Updated Lesson Title")

        # 7. Test patch lesson as other instructor -> Should return 403
        response = self.client.patch(
            f"/lessons/{lesson_id}",
            json=patch_data,
            headers=self.other_instructor_headers
        )
        self.assertEqual(response.status_code, 403)

        # 8. Test delete lesson (Admin or Owner) -> DELETE /api/lessons/{id}
        # Delete using admin
        response = self.client.delete(f"/lessons/{lesson_id}", headers=self.admin_headers)
        self.assertEqual(response.status_code, 204)

        # Verify deletion
        response = self.client.get(f"/lessons/{lesson_id}")
        self.assertEqual(response.status_code, 404)

    # ==========================================
    # ENROLLMENT & PROGRESS TESTS
    # ==========================================
    def test_enrollment_and_progress_flow(self):
        """Test student enrolling in a course and marking lesson progress."""
        course = Course.objects.create(
            title="LMS Integration Course",
            description="LMS Integration Flow",
            instructor=self.instructor
        )
        lesson1 = Lesson.objects.create(
            course=course,
            title="Lesson 1",
            content="Content 1",
            order=1
        )
        lesson2 = Lesson.objects.create(
            course=course,
            title="Lesson 2",
            content="Content 2",
            order=2
        )

        # 1. Enroll in course -> POST /api/enrollments
        enroll_data = {"course_id": course.id}
        response = self.client.post("/enrollments", json=enroll_data, headers=self.student_headers)
        self.assertEqual(response.status_code, 201)
        enrollment_id = response.json()["id"]

        # Double enroll -> Should return 409
        response = self.client.post("/enrollments", json=enroll_data, headers=self.student_headers)
        self.assertEqual(response.status_code, 409)

        # 2. Check student's enrolled courses -> GET /api/enrollments/my-courses
        response = self.client.get("/enrollments/my-courses", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["lessons_total"], 2)
        self.assertEqual(response.json()[0]["lessons_completed"], 0)

        # 3. Mark progress for Lesson 1 -> POST /api/enrollments/{id}/progress
        progress_data = {"lesson_id": lesson1.id, "completed": True}
        response = self.client.post(
            f"/enrollments/{enrollment_id}/progress",
            json=progress_data,
            headers=self.student_headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["completed"])

        # Check progress updated
        response = self.client.get("/enrollments/my-courses", headers=self.student_headers)
        self.assertEqual(response.json()[0]["lessons_completed"], 1)
        self.assertEqual(response.json()[0]["progress_percentage"], 50.0)

    # ==========================================
    # SEARCH, FILTER, SORT TESTS (Paket 1)
    # ==========================================
    def test_list_courses_filter_by_level_and_status(self):
        """Test filtering course list by level and status query params."""
        Course.objects.create(
            title="Django Beginner", description="Basic Django",
            instructor=self.instructor, category=self.category,
            level="beginner", status="published",
        )
        Course.objects.create(
            title="Django Advanced", description="Advanced Django",
            instructor=self.instructor, category=self.category,
            level="advanced", status="published",
        )
        Course.objects.create(
            title="Django Draft Course", description="Not ready yet",
            instructor=self.instructor, category=self.category,
            level="advanced", status="draft",
        )

        # Filter by level=advanced -> should return 2 (published + draft)
        response = self.client.get("/courses?level=advanced")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 2)

        # Filter by level=advanced AND status=published -> should return 1
        response = self.client.get("/courses?level=advanced&status=published")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["title"], "Django Advanced")

        # Filter by status=draft -> should return 1
        response = self.client.get("/courses?status=draft")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)

    def test_list_courses_search_by_keyword(self):
        """Test searching course list by title keyword."""
        Course.objects.create(
            title="Python for Beginners", description="Learn Python",
            instructor=self.instructor, category=self.category,
        )
        Course.objects.create(
            title="JavaScript Essentials", description="Learn JS",
            instructor=self.instructor, category=self.category,
        )

        response = self.client.get("/courses?search=Python")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["title"], "Python for Beginners")

    def test_list_courses_sort_by_rating(self):
        """Test sort=rating orders courses by average review rating descending."""
        course_low = Course.objects.create(
            title="Low Rated Course", description="desc",
            instructor=self.instructor, category=self.category,
        )
        course_high = Course.objects.create(
            title="High Rated Course", description="desc",
            instructor=self.instructor, category=self.category,
        )

        # Student enrolls and reviews both courses
        Enrollment.objects.create(student=self.student, course=course_low)
        Enrollment.objects.create(student=self.student, course=course_high)
        Review.objects.create(student=self.student, course=course_low, rating=2)
        Review.objects.create(student=self.student, course=course_high, rating=5)

        response = self.client.get("/courses?sort=rating")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(items[0]["title"], "High Rated Course")

    # ==========================================
    # CURRICULUM / SECTION TESTS (Paket 1)
    # ==========================================
    def test_create_section_as_owner_instructor(self):
        """Test instructor owner can create a section under their own course."""
        course = Course.objects.create(
            title="Curriculum Course", description="desc",
            instructor=self.instructor,
        )
        data = {"title": "Section 1: Introduction", "order": 1}
        response = self.client.post(
            f"/courses/{course.id}/sections", json=data, headers=self.instructor_headers
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Section 1: Introduction")

    def test_create_section_forbidden_for_non_owner_instructor(self):
        """Test non-owner instructor cannot create a section (returns 403)."""
        course = Course.objects.create(
            title="Curriculum Course 2", description="desc",
            instructor=self.instructor,
        )
        data = {"title": "Section X", "order": 1}
        response = self.client.post(
            f"/courses/{course.id}/sections", json=data, headers=self.other_instructor_headers
        )
        self.assertEqual(response.status_code, 403)

    def test_create_section_forbidden_for_student(self):
        """Test student role cannot create a section (returns 403)."""
        course = Course.objects.create(
            title="Curriculum Course 3", description="desc",
            instructor=self.instructor,
        )
        data = {"title": "Section X", "order": 1}
        response = self.client.post(
            f"/courses/{course.id}/sections", json=data, headers=self.student_headers
        )
        self.assertEqual(response.status_code, 403)

    def test_get_curriculum_public_with_nested_lessons(self):
        """Test curriculum endpoint is public and returns sections with nested lessons."""
        course = Course.objects.create(
            title="Curriculum Course 4", description="desc",
            instructor=self.instructor,
        )
        section = Section.objects.create(course=course, title="Section 1", order=1)
        Lesson.objects.create(
            course=course, section=section, title="Lesson A", content="content", order=1
        )
        Lesson.objects.create(
            course=course, section=section, title="Lesson B", content="content", order=2
        )

        response = self.client.get(f"/courses/{course.id}/curriculum")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Section 1")
        self.assertEqual(len(data[0]["lessons"]), 2)

    # ==========================================
    # REVIEW TESTS (Paket 1)
    # ==========================================
    def test_create_review_requires_enrollment(self):
        """Test student who has not enrolled cannot leave a review (returns 403)."""
        course = Course.objects.create(
            title="Review Course", description="desc", instructor=self.instructor
        )
        data = {"rating": 5, "comment": "Great course!"}
        response = self.client.post(
            f"/courses/{course.id}/reviews", json=data, headers=self.student_headers
        )
        self.assertEqual(response.status_code, 403)

    def test_create_review_success_after_enrollment(self):
        """Test enrolled student can successfully leave a review."""
        course = Course.objects.create(
            title="Review Course 2", description="desc", instructor=self.instructor
        )
        Enrollment.objects.create(student=self.student, course=course)

        data = {"rating": 4, "comment": "Pretty good"}
        response = self.client.post(
            f"/courses/{course.id}/reviews", json=data, headers=self.student_headers
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["rating"], 4)
        self.assertEqual(response.json()["student"]["username"], "student_test")

    def test_create_review_invalid_rating_rejected(self):
        """Test rating outside 1-5 range returns 400."""
        course = Course.objects.create(
            title="Review Course 3", description="desc", instructor=self.instructor
        )
        Enrollment.objects.create(student=self.student, course=course)

        data = {"rating": 9, "comment": "Too high"}
        response = self.client.post(
            f"/courses/{course.id}/reviews", json=data, headers=self.student_headers
        )
        self.assertEqual(response.status_code, 400)

    def test_review_duplicate_updates_instead_of_creating_new(self):
        """Test submitting a second review from the same student updates the existing one."""
        course = Course.objects.create(
            title="Review Course 4", description="desc", instructor=self.instructor
        )
        Enrollment.objects.create(student=self.student, course=course)

        self.client.post(
            f"/courses/{course.id}/reviews",
            json={"rating": 3, "comment": "Okay"},
            headers=self.student_headers,
        )
        response = self.client.post(
            f"/courses/{course.id}/reviews",
            json={"rating": 5, "comment": "Changed my mind, love it"},
            headers=self.student_headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Review.objects.filter(student=self.student, course=course).count(), 1)
        self.assertEqual(
            Review.objects.get(student=self.student, course=course).rating, 5
        )

    def test_list_reviews_public(self):
        """Test listing reviews for a course is public (no auth required)."""
        course = Course.objects.create(
            title="Review Course 5", description="desc", instructor=self.instructor
        )
        Enrollment.objects.create(student=self.student, course=course)
        Review.objects.create(student=self.student, course=course, rating=5, comment="Nice")

        response = self.client.get(f"/courses/{course.id}/reviews")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["rating"], 5)

    # ==========================================
    # WISHLIST TESTS (Paket 1)
    # ==========================================
    def test_add_course_to_wishlist(self):
        """Test student can add a course to their wishlist."""
        course = Course.objects.create(
            title="Wishlist Course", description="desc", instructor=self.instructor
        )
        response = self.client.post(f"/wishlist/{course.id}", headers=self.student_headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["course"]["title"], "Wishlist Course")

    def test_add_duplicate_wishlist_rejected(self):
        """Test adding the same course twice to wishlist returns 400."""
        course = Course.objects.create(
            title="Wishlist Course 2", description="desc", instructor=self.instructor
        )
        self.client.post(f"/wishlist/{course.id}", headers=self.student_headers)
        response = self.client.post(f"/wishlist/{course.id}", headers=self.student_headers)
        self.assertEqual(response.status_code, 400)

    def test_remove_course_from_wishlist(self):
        """Test student can remove a course from their wishlist."""
        course = Course.objects.create(
            title="Wishlist Course 3", description="desc", instructor=self.instructor
        )
        Wishlist.objects.create(student=self.student, course=course)

        response = self.client.delete(f"/wishlist/{course.id}", headers=self.student_headers)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            Wishlist.objects.filter(student=self.student, course=course).exists()
        )

    def test_remove_nonexistent_wishlist_returns_404(self):
        """Test removing a course that isn't in the wishlist returns 404."""
        course = Course.objects.create(
            title="Wishlist Course 4", description="desc", instructor=self.instructor
        )
        response = self.client.delete(f"/wishlist/{course.id}", headers=self.student_headers)
        self.assertEqual(response.status_code, 404)

    def test_list_my_wishlist(self):
        """Test student can list all courses in their own wishlist."""
        course1 = Course.objects.create(
            title="Wishlist Course 5", description="desc", instructor=self.instructor
        )
        course2 = Course.objects.create(
            title="Wishlist Course 6", description="desc", instructor=self.instructor
        )
        Wishlist.objects.create(student=self.student, course=course1)
        Wishlist.objects.create(student=self.student, course=course2)

        response = self.client.get("/wishlist", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_wishlist_forbidden_for_instructor(self):
        """Test instructor role cannot use wishlist endpoints (student-only feature)."""
        course = Course.objects.create(
            title="Wishlist Course 7", description="desc", instructor=self.instructor
        )
        response = self.client.post(f"/wishlist/{course.id}", headers=self.instructor_headers)
        self.assertEqual(response.status_code, 403)

    # ==========================================
    # STUDENT DASHBOARD TESTS (Paket 1)
    # ==========================================
    def test_student_dashboard_requires_auth(self):
        """Test dashboard endpoint requires authentication (returns 401)."""
        response = self.client.get("/students/me/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_student_dashboard_forbidden_for_instructor(self):
        """Test dashboard endpoint is student-only (instructor gets 403)."""
        response = self.client.get("/students/me/dashboard", headers=self.instructor_headers)
        self.assertEqual(response.status_code, 403)

    def test_student_dashboard_splits_active_and_completed_courses(self):
        """Test dashboard correctly separates active vs. completed courses based on progress."""
        # Course A: fully completed
        course_a = Course.objects.create(
            title="Dashboard Course A", description="desc", instructor=self.instructor
        )
        lesson_a1 = Lesson.objects.create(course=course_a, title="A1", content="c", order=1)
        Enrollment.objects.create(student=self.student, course=course_a)
        Progress.objects.create(student=self.student, lesson=lesson_a1, completed=True)

        # Course B: still in progress
        course_b = Course.objects.create(
            title="Dashboard Course B", description="desc", instructor=self.instructor
        )
        Lesson.objects.create(course=course_b, title="B1", content="c", order=1)
        Lesson.objects.create(course=course_b, title="B2", content="c", order=2)
        Enrollment.objects.create(student=self.student, course=course_b)

        response = self.client.get("/students/me/dashboard", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data["completed_courses"]), 1)
        self.assertEqual(data["completed_courses"][0]["course"]["title"], "Dashboard Course A")
        self.assertEqual(data["completed_courses"][0]["progress_percentage"], 100.0)

        self.assertEqual(len(data["active_courses"]), 1)
        self.assertEqual(data["active_courses"][0]["course"]["title"], "Dashboard Course B")
        self.assertEqual(data["active_courses"][0]["progress_percentage"], 0.0)

        self.assertEqual(data["total_courses_enrolled"], 2)

    def test_student_dashboard_wishlist_count(self):
        """Test dashboard reports the correct wishlist count."""
        course1 = Course.objects.create(
            title="Dashboard Wishlist 1", description="desc", instructor=self.instructor
        )
        course2 = Course.objects.create(
            title="Dashboard Wishlist 2", description="desc", instructor=self.instructor
        )
        Wishlist.objects.create(student=self.student, course=course1)
        Wishlist.objects.create(student=self.student, course=course2)

        response = self.client.get("/students/me/dashboard", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["wishlist_count"], 2)

    def test_student_dashboard_recommendations_exclude_enrolled_courses(self):
        """Test recommended_courses only suggests same-category courses the student hasn't taken."""
        # Student enrolls in a course under self.category
        enrolled_course = Course.objects.create(
            title="Enrolled Course", description="desc",
            instructor=self.instructor, category=self.category, status="published",
        )
        Enrollment.objects.create(student=self.student, course=enrolled_course)

        # Another published course, same category, not enrolled -> should be recommended
        other_course = Course.objects.create(
            title="Other Course Same Category", description="desc",
            instructor=self.instructor, category=self.category, status="published",
        )

        # A draft course in the same category -> should NOT be recommended
        Course.objects.create(
            title="Draft Course Same Category", description="desc",
            instructor=self.instructor, category=self.category, status="draft",
        )

        response = self.client.get("/students/me/dashboard", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        recommended_titles = [c["title"] for c in response.json()["recommended_courses"]]

        self.assertIn("Other Course Same Category", recommended_titles)
        self.assertNotIn("Enrolled Course", recommended_titles)
        self.assertNotIn("Draft Course Same Category", recommended_titles)