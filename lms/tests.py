from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from ninja.testing import TestClient

from lms.api import api
from lms.models import Course, Lesson, Enrollment, Progress, Category
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
