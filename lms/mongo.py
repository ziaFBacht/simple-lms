"""
MongoDB Integration untuk Simple LMS.

MongoDB dipakai untuk data yang TIDAK cocok di relational database:
- Activity Log   : setiap aksi user (login, enroll, mark_progress, dll)
  → skema berubah-ubah, volume tinggi, jarang di-query terstruktur
- Learning Analytics : ringkasan statistik pembelajaran per course/student
  → document model lebih fleksibel untuk shape data yang beragam

Koneksi:
  mongo_db() → mengembalikan instance pymongo.Database
  Dibuat lazy (connect saat pertama kali dipanggil) supaya tidak
  menghambat startup kalau MongoDB belum ready.

Collections:
  activity_logs       → log setiap user action
  learning_analytics  → aggregated learning data per course
"""
from datetime import datetime, timezone
from typing import Any

from django.conf import settings


def mongo_db():
    """Return pymongo database instance (lazy connect)."""
    from pymongo import MongoClient
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    return client[settings.MONGO_DB]


# ============================================================
# ACTIVITY LOG COLLECTION
# ============================================================
# Schema (tidak dipaksakan oleh MongoDB, ini hanya konvensi):
# {
#   "user_id":    int,
#   "username":   str,
#   "action":     str,   # "login" | "register" | "enroll" | "mark_progress" | "create_course" | ...
#   "detail":     dict,  # payload tambahan sesuai action
#   "ip":         str,
#   "timestamp":  datetime
# }

def log_activity(user_id: int, username: str, action: str, detail: dict = None, ip: str = ""):
    """
    Simpan activity log ke MongoDB.
    Dipanggil dari endpoint (tanpa blocking) atau dari Celery task.
    """
    try:
        db = mongo_db()
        doc = {
            "user_id":   user_id,
            "username":  username,
            "action":    action,
            "detail":    detail or {},
            "ip":        ip,
            "timestamp": datetime.now(timezone.utc),
        }
        db["activity_logs"].insert_one(doc)
    except Exception as e:
        # Jangan sampai error MongoDB menghentikan request utama
        print(f"[MONGO WARNING] log_activity failed: {e}")


def get_user_activities(user_id: int, limit: int = 20) -> list:
    """Ambil log aktivitas terbaru untuk satu user."""
    try:
        db = mongo_db()
        docs = (
            db["activity_logs"]
            .find({"user_id": user_id}, {"_id": 0})
            .sort("timestamp", -1)
            .limit(limit)
        )
        return list(docs)
    except Exception as e:
        print(f"[MONGO WARNING] get_user_activities failed: {e}")
        return []


# ============================================================
# LEARNING ANALYTICS COLLECTION
# ============================================================
# Schema:
# {
#   "course_id":          int,
#   "course_title":       str,
#   "total_students":     int,
#   "total_lessons":      int,
#   "completion_rates":   [{"student_id": int, "percentage": float}],
#   "avg_completion":     float,
#   "last_updated":       datetime
# }

def upsert_course_analytics(
    course_id: int,
    course_title: str,
    total_students: int,
    total_lessons: int,
    avg_completion: float,
):
    """
    Insert atau update dokumen analytics untuk sebuah course.
    Dipanggil dari Celery task `update_course_statistics`.
    """
    try:
        db = mongo_db()
        db["learning_analytics"].update_one(
            {"course_id": course_id},
            {
                "$set": {
                    "course_title":    course_title,
                    "total_students":  total_students,
                    "total_lessons":   total_lessons,
                    "avg_completion":  avg_completion,
                    "last_updated":    datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except Exception as e:
        print(f"[MONGO WARNING] upsert_course_analytics failed: {e}")


def get_course_analytics(course_id: int) -> dict:
    """Ambil analytics untuk satu course, atau dict kosong jika belum ada."""
    try:
        db = mongo_db()
        doc = db["learning_analytics"].find_one({"course_id": course_id}, {"_id": 0})
        return doc or {}
    except Exception as e:
        print(f"[MONGO WARNING] get_course_analytics failed: {e}")
        return {}


# ============================================================
# AGGREGATION QUERIES (untuk report)
# ============================================================

def aggregate_top_courses(limit: int = 5) -> list:
    """
    Top N course berdasarkan jumlah student terbanyak.
    Contoh aggregation pipeline MongoDB.
    """
    try:
        db = mongo_db()
        pipeline = [
            {"$sort": {"total_students": -1}},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "course_id": 1,
                "course_title": 1,
                "total_students": 1,
                "avg_completion": 1,
            }},
        ]
        return list(db["learning_analytics"].aggregate(pipeline))
    except Exception as e:
        print(f"[MONGO WARNING] aggregate_top_courses failed: {e}")
        return []


def aggregate_activity_summary(days: int = 7) -> list:
    """
    Hitung jumlah activity per action dalam N hari terakhir.
    Contoh aggregation dengan $group dan $dateToString.
    """
    from datetime import timedelta
    try:
        db = mongo_db()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$action",
                "count": {"$sum": 1},
            }},
            {"$sort": {"count": -1}},
            {"$project": {"_id": 0, "action": "$_id", "count": 1}},
        ]
        return list(db["activity_logs"].aggregate(pipeline))
    except Exception as e:
        print(f"[MONGO WARNING] aggregate_activity_summary failed: {e}")
        return []
