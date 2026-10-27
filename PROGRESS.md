# Nhật ký tiến độ StudyMate AI

Ghi lại việc đã làm, quyết định khác với `spec.md` gốc (và lý do), và việc còn thiếu.
Đây không phải tài liệu đặc tả — đặc tả đọc ở [spec.md](spec.md) và quy tắc ở [CLAUDE.md](CLAUDE.md).
Cập nhật file này sau mỗi task hoàn thành.

## Trạng thái tổng quan

| Bước (theo CLAUDE.md) | Trạng thái |
|---|---|
| 1. Database schema + pipeline nạp PDF | 🟡 Đang làm (Task 1, 2 xong — xem bên dưới) |
| 2. RAG Tutor Agent | ⬜ Chưa bắt đầu |
| 3. Supervisor + Quiz Agent | ⬜ Chưa bắt đầu |
| 4. Study Planner Agent | ⬜ Chưa bắt đầu |
| 5. Frontend | ⬜ Chưa bắt đầu |

## Quyết định khác với spec gốc (quan trọng, đừng revert)

- **LLM provider: Google Gemini**, không dùng $6 credit OpenAI còn lại (để dành cho giai đoạn đánh giá cuối nếu cần so sánh chất lượng).
- **Embedding model: `gemini-embedding-001`** (768 chiều, có chuẩn hoá L2), không dùng `text-embedding-004` như draft ban đầu — model đó đã ngừng hỗ trợ.
- **SDK: `google-genai`**, không dùng `google-generativeai` — thư viện cũ đã deprecated.
- **DB: Supabase qua Connection Pooler** (`*.pooler.supabase.com:6543`), không dùng host `db.<ref>.supabase.co:5432` trực tiếp — host trực tiếp chỉ có IPv6, máy dev không kết nối được (lỗi "could not translate host name").
- **Không dùng Docker** cho DB — máy dev cấu hình yếu, dùng Supabase Cloud thay thế. `CLAUDE.md` mục 4 vẫn còn ghi lệnh Docker, cần sửa khi làm tới bước deploy.
- **File storage: Supabase Storage**, bucket `documents` (private), tạo tự động ở lần upload đầu.

## Việc đã làm

### Task 1 — Database schema (xong)
- `backend/app/db.py`, `backend/app/config.py`: kết nối SQLAlchemy, đọc `.env` ở gốc dự án.
- `backend/app/models.py`: bảng `documents`, `document_chunks` (embedding `Vector(768)`, index HNSW cosine, cascade delete).
- `backend/init_db.py`: bật extension `vector`, tạo bảng trên Supabase.
- Đã test: kết nối thành công qua pooler, bảng đã tạo trên Supabase.

### Task 2 — PDF ingestion & embedding pipeline (xong, kiểm thử lại + bổ sung CORS)
- `backend/app/services/pdf_service.py`: trích xuất PyMuPDF (giữ `page_number`, nhận diện `section` từ mục lục PDF hoặc heuristic cỡ chữ/in đậm), chunk 500-800 token / overlap 80-120 (tiktoken `o200k_base`, không có tokenizer Gemini offline nên dùng tạm để ước lượng).
- `backend/app/services/embedding_service.py`: gọi Gemini, batch + retry (backoff tới 5 lần).
- `backend/app/services/storage_service.py`: upload PDF gốc lên Supabase Storage qua REST API.
- `backend/app/services/ingestion_service.py`: nối các bước, cập nhật `status` (`processing` → `indexed`/`failed`).
- `backend/app/auth.py`: xác thực qua Supabase Auth token (không tin `user_id` từ client). Có `DEV_USER_ID` trong `.env` để test không cần login (chỉ dùng dev).
- `backend/app/routers/documents.py` + `main.py`: `POST /api/documents/upload`.
- Đã test: trích xuất + chunk trên PDF tiếng Việt tự tạo (có/không mục lục) — đúng số tiêu đề, overlap đúng. Gọi Gemini embedding thật (768 chiều, đã chuẩn hoá). Các case lỗi (không token, không phải PDF, file rỗng) trả đúng mã lỗi.
- `backend/app/main.py`, `backend/app/config.py`: bổ sung `CORSMiddleware` (origin mặc định `http://localhost:3000`, đổi qua `CORS_ORIGINS` trong `.env`, nhiều origin cách nhau bằng dấu phẩy) để chuẩn bị cho Next.js gọi API.
- Đã test lại: health check, CORS preflight, upload không token → 401 — đều đúng. Server khởi động sạch với cấu hình mới.
- **Known issue**: `sample_docs/SachCSDL_bannop.pdf` là bản scan (không có lớp text) → sẽ báo lỗi 422, cần giáo trình PDF có text thật để test.
- **Đã test thật với dữ liệu production**: user upload giáo trình CSDL thật (63 trang, "Bài 1..6") qua Swagger → chạy hết pipeline, `status=indexed`, 49 chunk, đều có embedding. Rà soát trực tiếp trong Supabase phát hiện 2 lỗi ở `pdf_service.py`, đã sửa cả hai và re-index lại đúng (không cần upload lại):
  1. `_CHAPTER_PATTERN` chỉ nhận "Chương/Phần/Chapter/Part", không nhận "Bài" → tiêu đề "BÀI 1" bị tiêu đề con ngay sau đè mất. Đã thêm "bài/lesson/unit" vào pattern.
  2. Dòng trong trang Mục lục (dạng "Bài 1: Tên .......... 5") bị nhận nhầm thành tiêu đề thật → làm sai lệch cả `chapter` context cho các trang sau (vd. "LỜI NÓI ĐẦU" bị gắn nhầm thành con của "BÀI 6"). Đã thêm `_TOC_DOT_LEADER_PATTERN` để loại các dòng có chấm dẫn + số trang cuối dòng khỏi heuristic nhận diện tiêu đề.
  3. (phụ) Câu lệnh SQL in đậm viết hoa (`SELECT * FROM EMP`) bị nhận nhầm thành tiêu đề vì trùng điều kiện bold+uppercase. Đã thêm điều kiện: nhánh fallback bold+uppercase chỉ tính là tiêu đề khi có ký tự có dấu tiếng Việt (tiêu đề thật luôn có dấu, code/SQL thì không).
- **Known limitation (không phải bug)**: ~50% chunk dưới 500 token vì luật tự đặt "không để chunk vắt qua 2 mục" — giáo trình có nhiều mục con ngắn. Cần bộ câu hỏi đánh giá thực tế để quyết định có nới luật này không (spec đã ghi rõ 500-800 chỉ là điểm xuất phát).

## Việc còn thiếu / cần làm tiếp

- Bảng `profiles` (chưa có FK từ `documents.owner_id`).
- OCR cho PDF scan (spec ghi rõ: để giai đoạn sau).
- RAG Tutor Agent, Quiz Agent, Study Planner Agent — chưa viết dòng nào.
- Frontend — chưa khởi tạo.
- Bộ câu hỏi đánh giá RAG (~50 câu) — chưa chuẩn bị.
