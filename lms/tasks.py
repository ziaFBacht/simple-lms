"""
Celery Tasks untuk Simple LMS.

Tasks yang tersedia:
1. send_enrollment_email     - Email konfirmasi saat student enroll ke course
2. generate_certificate      - Generate certificate PNG saat course selesai 100%
3. update_course_statistics  - Update analytics MongoDB (scheduled tiap jam)
4. export_course_report      - Export CSV report async (bisa dipanggil admin)

Pattern:
- Semua task memakai shared_task agar bisa diimport tanpa circular import.
- bind=True + self → supaya bisa retry kalau gagal (self.retry).
- max_retries=3, countdown=60 → retry 3x dengan jeda 60 detik.
- Django ORM bisa dipakai langsung karena Celery dikonfigurasi dengan
  Django settings (lihat config/celery.py).
"""
import csv
import io
import os
from datetime import datetime, timezone

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


# ============================================================
# TASK 1: send_enrollment_email
# ============================================================
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_enrollment_email(self, student_id: int, course_id: int):
    """
    Kirim email konfirmasi ke student setelah berhasil enroll ke course.

    Dipanggil dari: lms/api.py > enroll_course()
    Trigger: POST /api/enrollments

    Args:
        student_id: ID user student
        course_id : ID course yang di-enroll
    """
    try:
        from lms.models import Course, User
        student = User.objects.get(pk=student_id)
        course  = Course.objects.select_related('instructor').get(pk=course_id)

        subject = f"Selamat! Anda berhasil mendaftar ke course: {course.title}"
        message = (
            f"Halo {student.get_full_name() or student.username},\n\n"
            f"Anda telah berhasil mendaftar ke course berikut:\n\n"
            f"  Judul     : {course.title}\n"
            f"  Instruktur: {course.instructor.get_full_name() or course.instructor.username}\n"
            f"  Deskripsi : {course.description[:200]}...\n\n"
            f"Selamat belajar!\n\n"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[student.email],
            fail_silently=False,
        )

        # Log ke MongoDB
        from lms.mongo import log_activity
        log_activity(
            user_id=student_id,
            username=student.username,
            action="enrollment_email_sent",
            detail={"course_id": course_id, "course_title": course.title},
        )

        return {
            "status": "ok",
            "student": student.username,
            "course": course.title,
        }

    except Exception as exc:
        raise self.retry(exc=exc)


# ============================================================
# TASK 2: generate_certificate
# ============================================================
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_certificate(self, student_id: int, course_id: int):
    """
    Generate certificate PNG saat student menyelesaikan seluruh lesson course.

    Dipanggil dari: lms/api.py > mark_progress() saat progress = 100%
    Trigger: POST /api/enrollments/{id}/progress (jika semua lesson complete)

    File tersimpan di: media/certificates/cert_{student_id}_{course_id}.png
    """
    try:
        from lms.models import Course, Lesson, Progress, User
        student = User.objects.get(pk=student_id)
        course  = Course.objects.get(pk=course_id)

        # Verifikasi student benar-benar sudah 100%
        total_lessons = Lesson.objects.filter(course=course).count()
        completed     = Progress.objects.filter(
            student=student, lesson__course=course, completed=True
        ).count()

        if total_lessons == 0 or completed < total_lessons:
            return {
                "status": "skipped",
                "reason": f"Course belum selesai ({completed}/{total_lessons})",
            }

        # ---- Generate gambar certificate sederhana dengan Pillow ----
        from PIL import Image, ImageDraw, ImageFont

        WIDTH, HEIGHT = 1200, 800
        BG_COLOR = (255, 248, 220)      # cream
        GOLD     = (184, 134, 11)
        NAVY     = (20, 40, 100)

        img  = Image.new('RGB', (WIDTH, HEIGHT), color=BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Border ganda emas
        draw.rectangle([20, 20, WIDTH-20, HEIGHT-20], outline=GOLD, width=8)
        draw.rectangle([30, 30, WIDTH-30, HEIGHT-30], outline=GOLD, width=2)

        # Teks (gunakan font default PIL kalau font custom tidak ada)
        def draw_text(text, y, size=40, color=NAVY):
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
            except OSError:
                font = ImageFont.load_default()
            bbox  = draw.textbbox((0, 0), text, font=font)
            w     = bbox[2] - bbox[0]
            draw.text(((WIDTH - w) / 2, y), text, fill=color, font=font)

        draw_text("SERTIFIKAT PENYELESAIAN", 80,  size=52, color=GOLD)
        draw_text("Certificate of Completion", 150, size=28, color=NAVY)
        draw_text("Diberikan kepada:",          250, size=28)
        draw_text(
            student.get_full_name() or student.username,
            310, size=60, color=GOLD,
        )
        draw_text("Telah berhasil menyelesaikan course:", 420, size=28)
        draw_text(course.title, 480, size=40, color=NAVY)
        draw_text(
            f"Diselesaikan pada: {datetime.now(timezone.utc).strftime('%d %B %Y')}",
            620, size=26,
        )
        draw_text("— Tim Simple LMS —", 700, size=22, color=GOLD)

        # Simpan ke media/certificates/
        cert_dir = os.path.join(settings.MEDIA_ROOT, 'certificates')
        os.makedirs(cert_dir, exist_ok=True)
        filename  = f"cert_{student_id}_{course_id}.png"
        filepath  = os.path.join(cert_dir, filename)
        img.save(filepath, 'PNG')

        # Log ke MongoDB
        from lms.mongo import log_activity
        log_activity(
            user_id=student_id,
            username=student.username,
            action="certificate_generated",
            detail={"course_id": course_id, "file": filename},
        )

        return {
            "status": "ok",
            "file": filepath,
            "student": student.username,
            "course": course.title,
        }

    except Exception as exc:
        raise self.retry(exc=exc)


# ============================================================
# TASK 3: update_course_statistics (scheduled tiap jam)
# ============================================================
@shared_task
def update_course_statistics():
    """
    Hitung ulang statistik semua course dan simpan ke MongoDB.

    Dijadwalkan oleh Celery Beat setiap awal jam (lihat settings CELERY_BEAT_SCHEDULE).
    Tidak perlu parameter — memproses SEMUA course.

    Statistik yang dihitung per course:
    - total students yang enroll
    - total lessons
    - rata-rata persentase penyelesaian lesson dari semua student
    """
    from lms.models import Course, Enrollment, Lesson, Progress
    from lms.mongo import upsert_course_analytics

    courses = Course.objects.all()
    updated = 0

    for course in courses:
        total_students = Enrollment.objects.filter(course=course).count()
        total_lessons  = Lesson.objects.filter(course=course).count()

        if total_students == 0 or total_lessons == 0:
            avg_completion = 0.0
        else:
            # Rata-rata: (total completed progress dari semua student) / (total_students * total_lessons) * 100
            total_completed = Progress.objects.filter(
                lesson__course=course, completed=True
            ).count()
            avg_completion = round(
                (total_completed / (total_students * total_lessons)) * 100, 2
            )

        upsert_course_analytics(
            course_id=course.id,
            course_title=course.title,
            total_students=total_students,
            total_lessons=total_lessons,
            avg_completion=avg_completion,
        )
        updated += 1

    print(f"[update_course_statistics] Updated {updated} courses")
    return {"updated": updated}


# ============================================================
# TASK 4: export_course_report (async, dipanggil admin)
# ============================================================
@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def export_course_report(self, course_id: int, requested_by_user_id: int):
    """
    Generate CSV report untuk satu course secara async.

    Dipanggil dari: GET /api/reports/courses/{id}/export (admin endpoint)
    File disimpan di media/reports/ dan path-nya dikembalikan.

    CSV berisi:
    - Daftar semua student yang enroll
    - Jumlah lesson yang diselesaikan per student
    - Persentase penyelesaian
    - Tanggal enroll
    """
    try:
        from lms.models import Course, Enrollment, Lesson, Progress, User
        course = Course.objects.get(pk=course_id)
        enrollments = Enrollment.objects.filter(course=course).select_related('student')
        total_lessons = Lesson.objects.filter(course=course).count()

        rows = []
        for enrollment in enrollments:
            student   = enrollment.student
            completed = Progress.objects.filter(
                student=student, lesson__course=course, completed=True
            ).count()
            percentage = round((completed / total_lessons) * 100, 2) if total_lessons else 0

            rows.append({
                "student_id":       student.id,
                "username":         student.username,
                "full_name":        student.get_full_name(),
                "email":            student.email,
                "enrolled_at":      enrollment.enrolled_at.strftime('%Y-%m-%d %H:%M:%S'),
                "lessons_total":    total_lessons,
                "lessons_completed":completed,
                "completion_pct":   percentage,
            })

        # Tulis ke CSV in-memory lalu simpan ke file
        report_dir = os.path.join(settings.MEDIA_ROOT, 'reports')
        os.makedirs(report_dir, exist_ok=True)
        filename = f"report_course_{course_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(report_dir, filename)

        fieldnames = [
            "student_id", "username", "full_name", "email",
            "enrolled_at", "lessons_total", "lessons_completed", "completion_pct",
        ]
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # Log ke MongoDB
        from lms.mongo import log_activity
        log_activity(
            user_id=requested_by_user_id,
            username="admin",
            action="course_report_exported",
            detail={"course_id": course_id, "file": filename, "rows": len(rows)},
        )

        return {
            "status": "ok",
            "file": filepath,
            "rows": len(rows),
            "course": course.title,
        }

    except Exception as exc:
        raise self.retry(exc=exc)
