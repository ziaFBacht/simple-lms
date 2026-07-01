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
1. **PostgreSQL** sebagai database relasional utama untuk mengelola entitas User, Category, Course, Section, Lesson, Enrollment, Progress, Review, dan Wishlist secara konsisten.
2. **Redis** sebagai media in-memory caching untuk mempercepat response time dari endpoint publik serta menerapkan rate-limiting (60 request per menit per IP).
3. **MongoDB** sebagai NoSQL document-oriented storage untuk mencatat log aktivitas pengguna secara fleksibel dan menyimpan agregasi laporan analitik.
4. **RabbitMQ** sebagai message broker yang menjembatani server Django dengan background worker.
5. **Celery Worker & Celery Beat** sebagai background process untuk menangani pengiriman email asinkronus, pembuatan sertifikat kelulusan dalam bentuk PNG secara asinkronus, dan eksekusi task rekap statistik harian secara berkala.

Selain fondasi wajib, project ini diperluas dengan fitur **LMS Experience (Paket 1)** — search/filter/sorting lanjutan, curriculum berbasis section, rating & review, wishlist, dan student dashboard — agar pengalaman student dan instructor lebih lengkap dan mendekati LMS production nyata.

---

### 2. Fitur Dasar yang Sudah Berjalan (Fondasi)
Seluruh komponen dasar yang diwajibkan dalam penugasan telah diimplementasikan dengan lengkap dan berfungsi dengan baik:
* **Docker & Docker Compose:** Seluruh infrastruktur (web, db, redis, mongodb, rabbitmq, celery-worker, celery-beat, flower) didefinisikan secara orkestrasi di `docker-compose.yml` sehingga dapat dinyalakan secara instan menggunakan perintah `docker compose up --build`.
* **Database & Migrasi:** Menggunakan PostgreSQL versi 15 yang migrasi tabelnya berjalan otomatis ketika container Django pertama kali dinyalakan.
* **Authentication & Authorization (JWT):** Registrasi user baru menggunakan password hashing standar industri. Autentikasi dilindungi dengan sistem JWT (Access + Refresh Token) dengan validasi role yang ketat.
* **Role-Based Access Control (RBAC):** Pembagian hak akses secara detail untuk role **Admin**, **Instructor**, dan **Student**.
* **Endpoint REST API:**
  * CRUD Course (GET, POST, PATCH, DELETE) pada router `/api/courses`, termasuk filter `search`, `category_id`, `instructor_id`, `level`, `status`, dan `sort`.
  * CRUD Lesson (GET, POST, PATCH, DELETE) pada router `/api/lessons` dan `/api/courses/{course_id}/lessons`.
  * Curriculum berbasis Section (`/api/courses/{course_id}/sections`, `/api/courses/{course_id}/curriculum`).
  * Enrollment (POST `/api/enrollments` dan GET `/api/enrollments/my-courses`).
  * Progress Tracking (POST `/api/enrollments/{enrollment_id}/progress`).
  * Review & Wishlist (`/api/courses/{course_id}/reviews`, `/api/wishlist`).
  * Student Dashboard (`/api/students/me/dashboard`).
* **Dokumentasi API:** Ter-generate otomatis via Swagger UI yang dapat diakses langsung pada `http://localhost:8000/docs`.
* **Struktur Project & Environment:** Menggunakan clean code practice, pemisahan logic routing & schema, serta pengamanan kredensial sensitif (`SECRET_KEY`, `DEBUG`, database credentials) di dalam berkas `.env`.

---

### 3. Fitur Tambahan yang Dipilih (Opsional)
Kami mengimplementasikan paket fitur yang menunjang kualitas, performa, arsitektur backend, dan pengalaman pengguna:

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
| 10 | **Search, Filter, dan Sorting Lanjutan** | Course & Learning Experience | 12 | **Selesai** |
| 11 | **Curriculum dan Progress Belajar Detail (Section)** | Course & Learning Experience | 15 | **Selesai** |
| 12 | **Rating, Review, dan Wishlist Course** | Course & Learning Experience | 12 | **Selesai** |
| 13 | **Student Dashboard** | Course & Learning Experience | 12 | **Selesai** |

*Total Poin Fitur Tambahan: **163 Poin** (Memenuhi kriteria maksimal penilaian 50 poin — dihitung maksimal 50 sesuai ketentuan penugasan).*

---

### 4. Penjelasan Implementasi Fitur Utama

**Redis Caching & Invalidation.** Detail dan daftar course di-cache di Redis. Cache key untuk daftar course dibangun dari kombinasi seluruh parameter query (`search`, `category_id`, `instructor_id`, `level`, `status`, `sort`, `page`, `page_size`) sehingga setiap kombinasi filter memiliki entri cache sendiri dan tidak saling menimpa. Saat data course, lesson, atau review berubah (create/update/delete), sistem memanggil `invalidate_course_cache` untuk menghapus seluruh key list dan detail course terkait di Redis, memastikan request berikutnya selalu mendapat data terbaru.

**Celery Asynchronous Tasks.** Ketika student mendaftar course, task dikirim ke RabbitMQ secara asinkronus dan dieksekusi Celery worker untuk mengirim email notifikasi. Saat student menyelesaikan 100% materi, Celery memakai Pillow untuk merender sertifikat PNG di background.

**MongoDB Analytics & Logging.** Setiap aksi penting (login, registrasi, membuat course, enroll, menandai progress) direkam ke koleksi `activity_logs` di MongoDB. Admin dapat memanggil `/api/reports/analytics/activity-summary` untuk melihat rekapitulasi.

**Search, Filter, dan Sorting Lanjutan.** Endpoint `GET /api/courses` diperluas dengan parameter `level`, `status`, dan `sort` (`newest`, `popular`, `rating`) di atas parameter yang sudah ada (`search`, `category_id`, `instructor_id`). Query di-annotate menggunakan `Avg` dan `Count` dari Django ORM untuk menghitung `avg_rating`, `review_count`, dan `enrollment_count` langsung di level database (bukan di Python), sehingga sorting tetap efisien walau data bertambah banyak.

**Curriculum dan Progress Belajar Detail.** Model `Section` ditambahkan sebagai pengelompok `Lesson` di dalam sebuah `Course` (relasi `Course → Section → Lesson`). Instructor pemilik course dapat menyusun section (`POST /api/courses/{id}/sections`), dan siapa saja dapat melihat struktur curriculum lengkap beserta lesson di dalamnya lewat `GET /api/courses/{id}/curriculum` (public, nested response).

**Rating, Review, dan Wishlist Course.** Student yang **sudah enroll** di sebuah course dapat memberi rating (1–5) dan komentar lewat `POST /api/courses/{id}/reviews`; submit kedua kali otomatis meng-update review yang sama (satu review per student per course, ditegakkan dengan `unique_together` di level model). Wishlist (`/api/wishlist`) memungkinkan student menyimpan course favorit tanpa harus enroll, dengan validasi anti-duplikat.

**Student Dashboard.** Endpoint `GET /api/students/me/dashboard` (student only) meringkas seluruh aktivitas belajar: daftar course aktif (progress < 100%) dan selesai (progress 100%) lengkap dengan persentase progress masing-masing, jumlah course di wishlist, total course yang pernah di-enroll, serta rekomendasi hingga 5 course dari kategori yang sama dengan yang sudah diikuti, difilter hanya yang berstatus `published` dan belum pernah di-enroll, diurutkan berdasarkan rating tertinggi.

---

### 5. Cara Menjalankan Project
1. Pastikan **Docker Desktop** sedang berjalan di lokal komputer Anda.
2. Buka folder project di command prompt/terminal, lalu jalankan perintah:
   ```bash
   docker compose up --build
   ```
3. Secara otomatis semua container (PostgreSQL, MongoDB, Redis, RabbitMQ, Celery Beat, Celery Worker, Flower, dan Django) akan menyala, dan migration berjalan otomatis.
4. Akses endpoint API interaktif di: `http://localhost:8000/docs`.
5. (Opsional) Jalankan test suite otomatis:
   ```bash
   docker compose run web python manage.py test lms
   ```

---

### 6. Akun Demo Pengujian
Untuk mempermudah pengujian hak akses (RBAC), berikut adalah akun demo yang dapat didaftarkan atau digunakan:

| Role | Username | Password | Email | Deskripsi |
| :--- | :--- | :--- | :--- | :--- |
| **Admin** | `admin_demo` | `adminpass123` | `admin@simplelms.com` | Mengakses menu laporan, ekspor data, dan analitik MongoDB. |
| **Instructor** | `instructor_demo` | `instructorpass123` | `instructor@simplelms.com` | Membuat course & lesson, menyusun curriculum, mengelola course miliknya sendiri. |
| **Student** | `student_demo` | `studentpass123` | `student@simplelms.com` | Menonton materi, daftar course, memberi review, wishlist, dan melihat dashboard. |

---

### 7. Endpoint Penting untuk Diuji
* **`/api/auth/register` (POST):** Pendaftaran user baru dengan role `student` atau `instructor`.
* **`/api/auth/login` (POST):** Login untuk mendapatkan sepasang token JWT (`access` dan `refresh`).
* **`/api/courses` (GET / POST):** List course dengan cache Redis, filter (`search`, `category_id`, `instructor_id`, `level`, `status`), dan sorting (`sort=newest|popular|rating`); create course baru (khusus `instructor`).
* **`/api/courses/{course_id}/sections` (POST):** Membuat section curriculum baru (owner instructor only).
* **`/api/courses/{course_id}/curriculum` (GET):** Curriculum lengkap course (section + lesson bersarang), public.
* **`/api/courses/{course_id}/lessons` (POST):** Membuat lesson baru pada course (owner instructor only).
* **`/api/lessons/{lesson_id}` (PATCH / DELETE):** Memodifikasi atau menghapus materi lesson.
* **`/api/courses/{course_id}/reviews` (GET / POST):** Melihat/membuat review course (POST hanya untuk student yang sudah enroll).
* **`/api/wishlist` (GET / POST /{course_id} / DELETE /{course_id}):** Kelola wishlist student.
* **`/api/enrollments` (POST):** Pendaftaran course untuk student, memicu notifikasi email Celery secara asinkronus.
* **`/api/enrollments/{enrollment_id}/progress` (POST):** Menandai materi selesai, memicu generate sertifikat otomatis di background jika progress 100%.
* **`/api/students/me/dashboard` (GET):** Dashboard student — course aktif/selesai, wishlist count, dan rekomendasi course.

---

### 8. Bukti Pengujian (Screenshot / Test Results)
* Seluruh endpoint API terdokumentasi dengan baik menggunakan OpenAPI/Swagger di `/docs`, dikelompokkan per tag: Authentication, Courses, Lessons, Enrollments, Reports, Wishlist, Students.
* Testing otomatis (`lms/tests.py`) mencakup **34 unit & integration test** yang seluruhnya **PASS**, meliputi:
  * Authentication & JWT (register, login, refresh, me).
  * CRUD Course & Lesson beserta RBAC per role.
  * Enrollment & progress tracking.
  * Search/filter/sort course (`level`, `status`, `search`, `sort=rating`).
  * Curriculum/Section (ownership & permission).
  * Review (validasi enrollment, rating 1–5, update-bukan-duplikat).
  * Wishlist (duplikat, remove, list, role restriction).
  * Student Dashboard (pembagian active/completed, wishlist count, rekomendasi yang tepat).
* Jalankan dengan: `docker compose run web python manage.py test lms`.

---

### 9. Kendala dan Solusi
* **Kendala Konektivitas Layanan MongoDB & RabbitMQ:** Terkadang container Django menyala lebih cepat dibandingkan layanan database MongoDB dan message broker RabbitMQ saat pertama kali dijalankan, menyebabkan error koneksi di awal.
  **Solusi:** Menambahkan skrip inisialisasi healthcheck di container `web` (`docker-compose.yml`) menggunakan shell loop yang memeriksa ketersediaan port Redis & PostgreSQL sebelum server Django mulai beroperasi. Selain itu, seluruh pemanggilan MongoDB dan Celery dibungkus `try/except` agar endpoint utama tetap berhasil merespons meskipun layanan pendukung tersebut belum siap.
* **Kendala Cache Key Bertabrakan Setelah Menambah Filter Baru:** Setelah parameter `level`, `status`, dan `sort` ditambahkan ke `GET /api/courses`, key Redis lama (yang hanya berdasarkan `search`/`category_id`/`instructor_id`) berisiko mengembalikan hasil filter yang salah karena kombinasi baru tidak tercermin di key.
  **Solusi:** Cache key builder (`_key_course_list` di `lms/cache.py`) diperbarui untuk menyertakan seluruh parameter filter dan sorting, sehingga setiap kombinasi unik mendapat entri cache tersendiri.
* **Kendala Query N+1 pada Rekomendasi Dashboard:** Query rating rata-rata untuk rekomendasi course berpotensi menyebabkan query berulang per course bila dihitung di level Python.
  **Solusi:** Perhitungan `avg_rating` dan `review_count` dilakukan lewat `annotate(Avg(...), Count(...))` di level database, dikombinasikan dengan `select_related`/`prefetch_related` pada relasi instructor dan category.

---

### 10. Kesimpulan
Pengembangan Simple LMS Extended Backend ini memberikan pengalaman mendalam mengenai bagaimana merancang backend yang andal menggunakan arsitektur modular di Django. Penggunaan Redis secara signifikan mengurangi latency data publik, MongoDB memfasilitasi pencatatan aktivitas berskala besar secara fleksibel, dan Celery + RabbitMQ memastikan operasi-operasi berat (seperti email & rendering file) tidak mengganggu waktu tunggu respon dari client utama. Penambahan Paket 1 (LMS Experience) — curriculum berbasis section, review & wishlist, search/filter/sort lanjutan, serta student dashboard — melengkapi sisi pengalaman pengguna (student experience) yang sebelumnya belum tersentuh, sekaligus melatih penerapan Django ORM annotation, cache key design, dan RBAC yang konsisten pada fitur-fitur baru.