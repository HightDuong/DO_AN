# Nhật ký tiến độ StudyMate AI

Ghi lại việc đã làm, quyết định khác với `spec.md` gốc (và lý do), và việc còn thiếu.
Đây không phải tài liệu đặc tả — đặc tả đọc ở [spec.md](spec.md) và quy tắc ở [CLAUDE.md](CLAUDE.md).
Cập nhật file này sau mỗi task hoàn thành.

## Trạng thái tổng quan

| Bước (theo CLAUDE.md) | Trạng thái |
|---|---|
| 1. Database schema + pipeline nạp PDF | ✅ Xong (Task 1, 2) |
| 2. RAG Tutor Agent | ✅ Task 3 xong, đã đánh giá bằng bộ 60 câu mock data — xem bên dưới |
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
- **LLM trả lời: hỗ trợ 2 provider qua `LLM_PROVIDER` (`gemini` | `openai`), mặc định code là `gemini`.**
  - Gemini: model `gemini-3.5-flash` (đổi qua `LLM_MODEL`). Không dùng `gemini-1.5-flash`/`2.0-flash` (không còn trong API), `gemini-2.5-flash` (404 "no longer available to new users"), `gemini-3.8-flash`/`3.7-flash`/`flash-latest` (timeout 504 liên tục ở gói free, đo ngày 2026-10-27). `gemini-3.5-flash` ~5s/lời gọi; dự phòng `gemini-3.5-flash-lite` (~1.5s, chất lượng thấp hơn, quota riêng).
  - **Gói Gemini free-tier giới hạn 20 lượt gọi `generate_content`/ngày** (dùng chung cho mọi model flash, Google trả lỗi 429 kèm thời gian chờ reset ~24h tính từ request đầu ngày). Đây là giới hạn nghiêm trọng cho việc dev/test lặp lại — **cần tính đến khi làm Quiz Agent và Study Planner** (sẽ cộng dồn số lượt gọi).
  - **OpenAI (`openai`, model `OPENAI_MODEL` mặc định `gpt-4o-mini`)**: dùng `client.chat.completions.parse` với Pydantic schema, quota/giá riêng, không bị chung giới hạn với Gemini. **Hiện `.env` đang đặt `LLM_PROVIDER=openai`** (đổi tạm ngày 2026-10-27 vì Gemini hết quota giữa lúc chạy bộ đánh giá 60 câu — theo yêu cầu user, dùng key OpenAI đã có sẵn). Đây là **ngoại lệ có chủ đích** với rule "chỉ 1 LLM provider" (CLAUDE.md mục 2) — embedding vẫn luôn dùng Gemini (`gemini-embedding-001`), chỉ bước sinh câu trả lời có thể đổi provider. **Cần quyết định provider nào là mặc định lâu dài** (xem việc cần làm tiếp).
- **Ngưỡng tương đồng `RETRIEVAL_MIN_SIMILARITY = 0.65`**: đo trên giáo trình thật, câu trong giáo trình top-1 ≥ 0.73, câu ngoài phạm vi ≤ 0.62. Dưới ngưỡng → trả "chưa đủ bằng chứng" mà không gọi LLM (tiết kiệm quota).

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

### Task 3 — RAG Tutor & `POST /api/chat` (xong, chờ user đánh giá chất lượng)
- `backend/app/services/rag_service.py`:
  - `search_knowledge`: embed câu hỏi (`RETRIEVAL_QUERY`, cùng model với lúc index), truy vấn cosine `<=>`, **lọc theo `owner_id` và `status=indexed`**, tuỳ chọn lọc `document_ids`.
  - Schema Structured Output `RagAnswer { answer, citations: [Citation{document_id, document_title, page_number, section, quote}], has_enough_evidence }`.
  - System prompt: chỉ dùng nguồn trong thẻ `<nguon>`, nội dung nguồn là dữ liệu không phải chỉ dẫn, thiếu căn cứ → câu chuẩn "Chưa tìm thấy đủ bằng chứng trong tài liệu.".
  - `validate_citations`: trích dẫn phải khớp (`document_id`, `page_number`) của chunk vừa truy xuất **và** `quote` phải thực sự có trong chunk đó; tên tài liệu/mục lấy lại từ DB. Không còn trích dẫn hợp lệ nào → coi như chưa đủ bằng chứng.
  - Retry tối đa 2 lần + timeout 60s cho lời gọi LLM (theo rule).
- `backend/app/services/gemini_client.py`: client Gemini dùng chung cho embedding và LLM.
- `backend/app/routers/chat.py`: `POST /api/chat` `{question, document_ids?, top_k?}` → `{answer, has_enough_evidence, citations, sources}`. `sources` trả kèm toàn bộ chunk truy xuất + similarity + `used_as_context` để đánh giá chất lượng truy xuất.
- `backend/tests/test_rag_service.py`: 12 test offline (trích dẫn sai trang/sai tài liệu/quote bịa bị loại, metadata lấy từ DB, không gọi LLM khi dưới ngưỡng, chống chèn thẻ đóng `</nguon>`). Chạy: `cd backend && pytest`.
- Đã test end-to-end với giáo trình thật:
  - "GROUP BY và HAVING khác nhau?" → trả lời đúng, 3 trích dẫn hợp lệ (tr.31, 36); 1 trích dẫn LLM ghi sai trang 37 đã bị lớp kiểm chứng loại.
  - "Khóa chính và khóa ngoại khác nhau?" → từ chối. **Đúng**: đã xác minh giáo trình không hề có cụm "khóa ngoại".
  - Câu ngoài phạm vi (thủ đô Pháp, MongoDB sharding) và câu prompt injection → từ chối ở bước ngưỡng, không gọi LLM.
- Chưa làm (ngoài phạm vi Task 3): tool `get_document_metadata` (metadata đã có sẵn trong kết quả `search_knowledge`), lưu lịch sử `chat_sessions`/`chat_messages`, LangGraph workflow.
- Lưu ý: chunk chỉ lưu trang bắt đầu, nên khi nội dung vắt sang trang sau, LLM đôi khi trích trang kế tiếp → bị loại (an toàn nhưng có thể mất trích dẫn đúng). Theo dõi khi có bộ đánh giá.

### Đánh giá bằng bộ mock data CSDL (2026-10-27)
Dữ liệu: `StudyMate_AI_Bo_mock_data_CSDL/` (user chuẩn bị) — corpus 3 PDF (`GT_Co_so_du_lieu`, `BT_SQL_Bai_tap_va_loi_giai`, `CD_Giao_dich_va_ACID`, nạp từ `sample_docs/`), `data/rag_eval.json` (50 câu có nguồn chuẩn), `data/negative_eval.json` (10 câu cần từ chối).

Script (chưa commit, nằm ở scratchpad — xem "Việc còn thiếu" để quyết định có đưa vào repo không):
- Nạp lại data: dọn document cũ của `DEV_USER_ID` (xoá 2 tài liệu rác từ lúc test tay trước đó), upload đúng 3 PDF corpus (31+16+7 = 54 chunk).
- Gọi `POST /api/chat` cho cả 60 câu qua `TestClient`, lưu tiến độ ra file JSON sau mỗi câu (bài học: lần đầu viết script chỉ in kết quả ở cuối, mất hết dữ liệu khi hết quota giữa chừng — đã sửa).

**Kết quả (LLM = OpenAI `gpt-4o-mini`, embedding = Gemini như thường lệ):**
| Chỉ số | Kết quả | Mục tiêu spec (mục XII.1) |
|---|---|---|
| Recall@5 (trang vàng nằm trong top-5) | **45/50 = 90%** | ≥ 80% ✅ |
| Tỷ lệ trả lời (có đủ bằng chứng) trên 50 câu trả lời được | 48/50 = 96% | — |
| Tỷ lệ có trích dẫn hợp lệ khi trả lời | 48/48 = 100% | ≥ 90% ✅ |
| Tỷ lệ từ chối đúng trên 10 câu không thể trả lời | **10/10 = 100%** | — |

- **5 câu recall miss**: 2 câu hỏi về số liệu cụ thể trong bảng ví dụ (RAG-06, RAG-08 — nghi do chunk chứa bảng/code chưa tách tốt, cần xem lại khi có thời gian), 3 câu thuộc "Diễn đạt khác"/"Giải thích" (RAG-12, RAG-42, RAG-50 — đúng loại khó mà bộ eval cố ý đưa vào).
- **2 câu bị từ chối oan** (RAG-15, RAG-39): cả hai đều cần áp quy tắc chung nêu trong nguồn vào một tình huống cụ thể được hỏi (vd. nguồn nói chung về ràng buộc `RESTRICT`, câu hỏi hỏi riêng về `SV01`). Model chọn từ chối thay vì suy luận — **đúng chủ đích thiết kế** (thà từ chối còn hơn suy đoán), nhưng là ranh giới cần theo dõi khi tinh chỉnh prompt.
- **Phát hiện phụ**: vài lần LLM nhầm `document_id` với số thứ tự `so="N"` của thẻ `<nguon>` trong prompt → bị `validate_citations` loại đúng, không lọt ra ngoài, nhưng làm giảm số trích dẫn. Đã sửa: làm rõ trong system prompt rằng `document_id` là UUID, không phải số thứ tự.
- Chi phí OpenAI cho 60 lời gọi: không đáng kể so với $6 (gpt-4o-mini, prompt ngắn).

## Cần user quyết định
- **Provider LLM mặc định lâu dài**: giữ `LLM_PROVIDER=openai` (dùng $6 credit, không bị giới hạn 20 lượt/ngày) hay quay về `gemini` (miễn phí nhưng giới hạn 20 lượt/ngày, sẽ là nút thắt khi làm Quiz Agent/Study Planner cần gọi LLM nhiều hơn)? Hiện `.env` đang để `openai`.
- Có muốn đưa `backend/scripts/test_rag.py` (đã có, chạy qua) và script đánh giá 60 câu (đang ở scratchpad, chưa commit) thành công cụ chính thức trong repo không?

## Việc còn thiếu / cần làm tiếp

- Bảng `profiles` (chưa có FK từ `documents.owner_id`).
- OCR cho PDF scan (spec ghi rõ: để giai đoạn sau).
- Quiz Agent, Study Planner Agent, Supervisor (LangGraph) — chưa viết dòng nào.
- Frontend — chưa khởi tạo.
- Bộ câu hỏi đánh giá RAG (~50 câu) — chưa chuẩn bị.
