# LAPORAN FINAL PROJECT
## Simple LMS Extended Backend

---

### Identitas Mahasiswa
* **Nama:** Faiz Bachtiar Bachtiar
* **NIM:** A11.2023.15044
* **Kelas:** A11.4602
* **URL Repository:** https://github.com/ziaFBacht/simple-lms

---

### 1. Deskripsi Project
Project ini adalah **Simple Learning Management System (LMS) Extended Backend** berbasis framework Django yang dikembangkan menggunakan **Django Ninja** untuk REST API yang cepat dan type-safe. 

Aplikasi ini dirancang dengan arsitektur modern berskala production-ready yang mengintegrasikan berbagai macam database dan broker penunjang:
1. **PostgreSQL** sebagai database relasional utama untuk mengelola entitas User, Category, Course, Lesson, Enrollment, dan Progress secara konsisten.
2. **Redis** sebagai media in-memory caching untuk mempercepat response time dari endpoint publik serta menerapkan rate-limiting (60 request per menit per IP).
3. **MongoDB** sebagai NoSQL document-oriented storage untuk mencatat log aktivitas pengguna secara fleksibel dan menyimpan agregasi laporan analitik.
4. **RabbitMQ** sebagai message broker yang menjembatani server Django dengan background worker.
5. **Celery Worker & Celery Beat** sebagai background process untuk menangani pengiriman email asinkronus, pembuatan sertifikat kelulusan dalam bentuk PNG secara asinkronus, dan eksekusi task rekap statistik harian secara berkala.

---

### 2. Fitur Dasar yang Sudah Berjalan (Fondasi)
Seluruh komponen dasar yang diwajibkan dalam penugasan telah diimplementasikan dengan lengkap dan berfungsi dengan baik:
* **Docker & Docker Compose:** Seluruh infrastruktur (web, db, redis, mongodb, rabbitmq, celery-worker, celery-beat, flower) didefinisikan secara orkestrasi di `docker-compose.yml` sehingga dapat dinyalakan secara instan menggunakan perintah `docker compose up --build`.
* **Database & Migrasi:** Menggunakan PostgreSQL versi 15 yang migrasi tabelnya berjalan otomatis ketika container Django pertama kali dinyalakan.
* **Authentication & Authorization (JWT):** Registrasi user baru menggunakan password hashing standar industri. Autentikasi dilindungi dengan sistem JWT (Access + Refresh Token) dengan validasi role yang ketat.
* **Role-Based Access Control (RBAC):** Pembagian hak akses secara detail untuk role **Admin**, **Instructor**, dan **Student**.
* **Endpoint REST API:** 
  * CRUD Course (GET, POST, PATCH, DELETE) pada router `/api/courses`.
  * CRUD Lesson (GET, POST, PATCH, DELETE) pada router `/api/lessons` dan `/api/courses/{course_id}/lessons`.
  * Enrollment (POST `/api/enrollments` dan GET `/api/enrollments/my-courses`).
  * Progress Tracking (POST `/api/enrollments/{enrollment_id}/progress`).
* **Dokumentasi API:** Ter-generate otomatis via Swagger UI yang dapat diakses langsung pada `http://localhost:8000/docs`.
* **Struktur Project & Environment:** Menggunakan clean code practice, pemisahan logic routing & schema, serta pengamanan kredensial sensitif (`SECRET_KEY`, `DEBUG`, database credentials) di dalam berkas `.env`.

---

### 3. Fitur Tambahan yang Dipilih (Opsional)
Kami mengimplementasikan paket fitur yang menunjang kualitas, performa, dan arsitektur backend:

| No | Fitur Tambahan | Kategori | Poin | Status |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Redis Caching untuk Course** | Redis, Caching, & Perf | 12 | **Selesai** |
| 2 | **Cache Invalidation Strategy** | Redis, Caching, & Perf | 12 | **Selesai** |
| 3 | **Optimasi Query & N+1 Fixing** | Redis, Caching, & Perf | 15 | **Selesai** |
| 4 | **Email Notification Async via Celery** | Celery & Async | 12 | **Selesai** |
| 5 | **Generate Certificate Async via Celery & Pillow** | Celery & Async | 18 | **Selesai** |
| 6 | **Scheduled Task via Celery Beat** | Celery & Async | 15 | **Selesai** |
| 7 | **Activity Logging ke MongoDB** | MongoDB & Analytics | 15 | **Selesai** |
| 8 | **Course Analytics Report** | MongoDB & Analytics | 15 | **Selesai** |
| 9 | **Flower Monitoring** | Celery & Async | 8 | **Selesai** |

*Total Poin Fitur Tambahan: **112 Poin** (Memenuhi kriteria maksimal penilaian 50 poin).*

---

### 4. Penjelasan Implementasi Fitur Utama
* **Redis Caching & Invalidation:** Detail dan daftar course di-cache di Redis database. Saat data course atau lesson mengalami perubahan (create, update, delete), sistem memanggil `invalidate_course_cache` untuk menghapus key list dan detail course di Redis agar request berikutnya mendapatkan data terbaru secara konsisten.
* **Celery Asynchronous Tasks:** Ketika student melakukan pendaftaran course, task dikirim ke RabbitMQ secara asinkronus dan dieksekusi oleh Celery worker untuk mengirim email notifikasi. Saat student menyelesaikan 100% materi (progress track complete), Celery mendownload engine Pillow untuk me-render data nama student & judul course ke dalam sertifikat PNG secara background process.
* **MongoDB Analytics & Logging:** Setiap user melakukan aksi login, registrasi, membuat course, enroll, dan menandai progress, datanya direkam ke MongoDB `activity_logs` collection. Admin dapat memanggil endpoint `/api/reports/analytics/activity-summary` untuk melihat rekapitulasi data tersebut.

---

### 5. Cara Menjalankan Project
1. Pastikan **Docker Desktop** sedang berjalan di lokal komputer Anda.
2. Buka folder project di command prompt/terminal, lalu jalankan perintah:
   ```bash
   docker compose up --build
   ```
3. Secara otomatis semua container (PostgreSQL, MongoDB, Redis, RabbitMQ, Celery Beat, Celery Worker, Flower, dan Django) akan menyala.
4. Akses endpoint API interaktif di: `http://localhost:8000/docs`.

---

### 6. Akun Demo Pengujian
Untuk mempermudah pengujian hak akses (RBAC), berikut adalah akun demo yang dapat didaftarkan atau digunakan:

| Role | Username | Password | Email | Deskripsi |
| :--- | :--- | :--- | :--- | :--- |
| **Admin** | `admin_demo` | `adminpass123` | `admin@simplelms.com` | Mengakses menu laporan, ekspor data, dan analitik MongoDB. |
| **Instructor** | `instructor_demo` | `instructorpass123` | `instructor@simplelms.com` | Membuat course & lesson, mengelola course miliknya sendiri. |
| **Student** | `student_demo` | `studentpass123` | `student@simplelms.com` | Menonton materi, daftar course, dan melacak progress kelulusan. |

---

### 7. Endpoint Penting untuk Diuji
* **`/api/auth/register` (POST):** Pendaftaran user baru dengan role `student` atau `instructor`.
* **`/api/auth/login` (POST):** Login untuk mendapatkan sepasang token JWT (`access` dan `refresh`).
* **`/api/courses` (GET / POST):** Melihat list course dengan cache Redis (respons <50ms) dan membuat course baru (khusus `instructor`).
* **`/api/courses/{course_id}/lessons` (POST):** Membuat lesson baru pada course (hanya bisa diakses oleh instructor pemilik course tersebut).
* **`/api/lessons/{lesson_id}` (PATCH / DELETE):** Memodifikasi atau menghapus materi lesson.
* **`/api/enrollments` (POST):** Pendaftaran course untuk student yang memicu notifikasi email Celery secara asinkronus.
* **`/api/enrollments/{enrollment_id}/progress` (POST):** Menandai materi selesai yang memicu generate sertifikat otomatis di background jika seluruh progress bernilai 100%.

---

### 8. Bukti Pengujian (Screenshot / Test Results)
* Seluruh endpoint API terdokumentasi dengan baik menggunakan OpenAPI/Swagger di `/docs`.
* Testing otomatis berjalan dan pass dengan cakupan unit test model, autentikasi, serta integrasi endpoint REST API.

---

### 9. Kendala dan Solusi
* **Kendala Konektivitas Layanan MongoDB & RabbitMQ:** Terkadang container Django menyala lebih cepat dibandingkan layanan database MongoDB dan message broker RabbitMQ saat pertama kali dijalankan, menyebabkan error koneksi di awal.
* **Solusi:** Menambahkan skrip inisialisasi healthcheck di container `web` (`docker-compose.yml`) menggunakan shell loop yang memeriksa ketersediaan port Redis & PostgreSQL sebelum server Django mulai beroperasi.

---

### 10. Kesimpulan
Pengembangan Simple LMS Extended Backend ini memberikan pengalaman mendalam mengenai bagaimana merancang backend yang andal menggunakan arsitektur modular di Django. Penggunaan Redis secara signifikan mengurangi latency data publik, MongoDB memfasilitasi pencatatan aktivitas berskala besar secara fleksibel, dan Celery + RabbitMQ memastikan operasi-operasi berat (seperti email & rendering file) tidak mengganggu waktu tunggu respon dari client utama.
