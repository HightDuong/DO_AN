# Nhật ký tiến độ StudyMate AI

Ghi lại việc đã làm, quyết định khác với `spec.md` gốc (và lý do), và việc còn thiếu.
Đây không phải tài liệu đặc tả — đặc tả đọc ở [spec.md](spec.md) và quy tắc ở [CLAUDE.md](CLAUDE.md).
Cập nhật file này sau mỗi task hoàn thành.

## Trạng thái tổng quan

| Bước (theo CLAUDE.md) | Trạng thái |
|---|---|
| 1. Database schema + pipeline nạp PDF | ✅ Xong (Task 1, 2) |
| 2. RAG Tutor Agent | ✅ Task 3 xong, đã đánh giá bằng bộ 60 câu mock data — xem bên dưới |
| 3. Supervisor + Quiz Agent | ✅ Task 4 xong (schema quiz, Quiz Agent, chấm điểm, mastery, LangGraph Supervisor, API) |
| 4. Study Planner Agent | ✅ Task 5 xong (Planner + `/api/chat` đi qua Supervisor 3 agent) |
| 4.5 Hoàn thiện backend cho demo | ✅ Task 5.5 xong (lịch sử chat, agent_runs, nhiệm vụ gắn mục/trang, seed hồ sơ demo) |
| 5. Frontend | ⬜ Chưa bắt đầu |

## Quyết định khác với spec gốc (quan trọng, đừng revert)

- **Embedding model: `gemini-embedding-001`** (768 chiều, có chuẩn hoá L2), không dùng `text-embedding-004` như draft ban đầu — model đó đã ngừng hỗ trợ.
- **SDK: `google-genai`**, không dùng `google-generativeai` — thư viện cũ đã deprecated.
- **DB: Supabase qua Connection Pooler** (`*.pooler.supabase.com:6543`), không dùng host `db.<ref>.supabase.co:5432` trực tiếp — host trực tiếp chỉ có IPv6, máy dev không kết nối được (lỗi "could not translate host name").
- **Không dùng Docker** cho DB — máy dev cấu hình yếu, dùng Supabase Cloud thay thế. `CLAUDE.md` mục 4 vẫn còn ghi lệnh Docker, cần sửa khi làm tới bước deploy.
- **File storage: Supabase Storage**, bucket `documents` (private), tạo tự động ở lần upload đầu.
- **LLM trả lời: `LLM_PROVIDER=openai` là mặc định lâu dài** (user quyết định 2026-10-27; code vẫn hỗ trợ `gemini` để dự phòng).
  - Gemini: model `gemini-3.5-flash` (đổi qua `LLM_MODEL`). Không dùng `gemini-1.5-flash`/`2.0-flash` (không còn trong API), `gemini-2.5-flash` (404 "no longer available to new users"), `gemini-3.8-flash`/`3.7-flash`/`flash-latest` (timeout 504 liên tục ở gói free, đo ngày 2026-10-27). `gemini-3.5-flash` ~5s/lời gọi; dự phòng `gemini-3.5-flash-lite` (~1.5s, chất lượng thấp hơn, quota riêng).
  - **Gói Gemini free-tier giới hạn 20 lượt gọi `generate_content`/ngày** (dùng chung cho mọi model flash, Google trả lỗi 429 kèm thời gian chờ reset ~24h tính từ request đầu ngày). Đây là giới hạn nghiêm trọng cho việc dev/test lặp lại — **cần tính đến khi làm Quiz Agent và Study Planner** (sẽ cộng dồn số lượt gọi).
  - **OpenAI (`OPENAI_MODEL`, mặc định `gpt-4o-mini`)**: dùng `client.chat.completions.parse` với Pydantic schema. Chuyển sang ngày 2026-10-27 vì Gemini free-tier hết quota giữa lúc chạy bộ đánh giá 60 câu. Đây là **ngoại lệ có chủ đích** với rule "chỉ 1 LLM provider" (CLAUDE.md mục 2): embedding vẫn luôn dùng Gemini (`gemini-embedding-001`), chỉ bước sinh nội dung (RAG, quiz, phân loại intent) dùng OpenAI.
  - Toàn bộ lời gọi LLM đi qua `app/services/llm_service.py::generate_structured(system, prompt, schema)` (timeout + retry tối đa 2 lần).
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

### Task 3 — RAG Tutor & `POST /api/chat` (xong)
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
- Chưa làm (ngoài phạm vi Task 3): tool `get_document_metadata` (metadata đã có sẵn trong kết quả `search_knowledge`), lưu lịch sử `chat_sessions`/`chat_messages`.
- Lưu ý: chunk chỉ lưu trang bắt đầu, nên khi nội dung vắt sang trang sau, LLM đôi khi trích trang kế tiếp → bị loại (an toàn nhưng có thể mất trích dẫn đúng). Theo dõi khi có bộ đánh giá.

### Task 4 — Quiz schema, Quiz Agent, LangGraph Supervisor (xong, 2026-10-27)
**Database** (`app/models.py`, đã tạo trên Supabase bằng `python init_db.py`):
- `quiz_sets` (creator_id, title, topic, question_count, difficulty), `quiz_questions` (options JSONB 4 phần tử theo thứ tự A-D, `correct_answer` 'A'-'D', explanation, topic, difficulty; CHECK đúng 4 phương án và đáp án hợp lệ), `quiz_question_sources` (PK question_id + chunk_id, FK `ON DELETE CASCADE` sang `document_chunks`), `quiz_attempts` (score 0-100, correct_count, total_questions, duration_seconds, status), `quiz_responses` (selected_answer NULL = bỏ trống, is_correct, points), `user_topic_mastery` (PK user_id + topic, mastery_score 0..1, attempts_count, correct_count, total_count, last_attempt_at).

**Quyết định thiết kế:**
- **Chủ đề cố định 5 giá trị** đúng như mock data: "Tổng quan", "Mô hình quan hệ", "Khóa và liên kết", "SQL", "Giao dịch" (enum `QuizTopic`). Độ khó: "Cơ bản", "Vận dụng" (giống `quiz_reference.json`). Để Study Planner đọc được `learner_profiles.json` mà không cần ánh xạ.
- **Đáp án lưu dạng chữ cái A-D** (giống mock data), không phải số thứ tự.
- **Mastery = tỷ lệ đúng tích luỹ** (`correct_count / total_count` qua mọi lần làm). Đơn giản, giải thích được. Hạn chế: làm lại cùng một đề nhiều lần (đã thấy đáp án) vẫn được tính, làm tăng mastery. Có thể đổi sang trọng số theo thời gian sau.
- **Chủ đề yếu** = mastery < `WEAK_TOPIC_THRESHOLD` (0.7).
- **Trích nguồn khi sinh đề**: chunk đưa vào prompt được gán mã ngắn `C1..C8`, LLM trả mã, server ánh xạ về `chunk_id` thật. Lý do: ở Task 3 LLM từng chép sai UUID; mã ngắn ít lỗi hơn và vẫn bảo đảm `chunk_id` lưu vào DB chắc chắn thuộc tập vừa truy xuất.
- **Trộn thứ tự 4 phương án phía server** sau khi kiểm tra: chạy thật thấy LLM đặt đáp án đúng chủ yếu ở A (5 câu: A, B, B, A, A). Vì vậy prompt cấm lời giải thích nhắc "đáp án A/B...", và code loại câu vi phạm.

**Quiz Agent** (`app/services/quiz_service.py`):
- `retrieve_topic_chunks`: mỗi chủ đề có 2-4 truy vấn bao quát (`TOPIC_QUERIES`), gộp kết quả, bỏ trùng, bỏ chunk dưới ngưỡng 0.65, giữ tối đa 8 chunk; lọc theo `owner_id`.
- `generate_quiz`: tối đa 2 vòng gọi LLM (vòng 2 chỉ bù số câu bị loại, kèm danh sách câu đã có để tránh trùng). Không có chunk liên quan thì báo lỗi ngay, không gọi LLM.
- `validate_generated_questions`: đúng 4 phương án không rỗng, không trùng; không có phương án kiểu "tất cả / không đáp án nào" (nguy cơ nhiều đáp án đúng); có giải thích, không nhắc chữ cái phương án; ít nhất 1 nguồn hợp lệ; không trùng câu đã có.
- `grade_attempt`: chấm bằng so sánh với `correct_answer` trong DB (không gọi LLM), câu bỏ trống tính sai, câu không thuộc đề trả lỗi 400. Lưu attempt + responses + cập nhật mastery trong **một transaction**; mastery dùng `INSERT ... ON CONFLICT DO NOTHING` rồi `SELECT ... FOR UPDATE` để hai bài nộp đồng thời không ghi đè nhau.
- `learning_summary`: số tài liệu đã index, số đề đã tạo, số lần làm, điểm TB, điểm gần nhất, 10 lần làm gần nhất, mastery 5 chủ đề, chủ đề yếu.

**Supervisor** (`app/agents/workflow.py`, LangGraph 1.2): `START -> classify_intent -> (rag_tutor | quiz_agent) -> END`.
- `classify_intent` dùng LLM (Structured Output: intent + topic/num_questions/difficulty nếu là quiz); LLM lỗi thì fallback phân loại bằng từ khoá.
- Quiz chưa rõ chủ đề: trả `clarification` hỏi lại, không sinh đề.
- Chống vòng lặp: đồ thị không có cạnh quay lui (test kiểm tra đúng tập cạnh), `recursion_limit=5`, mỗi lời gọi LLM có timeout + retry giới hạn. Lỗi trong agent trả về `result.type = "error"`, không làm sập workflow.
- Task 5: đã nối vào `POST /api/chat` và thêm nhánh `study_planner` (xem Task 5).

**API** (`app/routers/quizzes.py`):
- `POST /api/quizzes/generate` `{topic, num_questions 1-10, difficulty, document_ids?}`: 201, đề KHÔNG kèm đáp án.
- `GET /api/quizzes/{id}`: đề làm bài, ẩn `correct_answer`, `explanation`, nguồn. Chỉ người tạo đề truy cập được (người khác nhận 404).
- `POST /api/quizzes/{id}/attempts` `{answers: [{question_id, selected_answer A-D|null}], duration_seconds?}`: điểm, từng câu (đã chọn, đáp án đúng, giải thích, nguồn: tài liệu/trang/mục), mastery mới.
- `GET /api/learning-summary`.

**Kiểm thử:**
- `pytest`: **61 test pass** (12 RAG cũ + 31 quiz + 18 supervisor), tất cả offline (LLM, truy xuất, session đều giả).
- Chạy thật trên Supabase + OpenAI: sinh đề SQL 5 câu (~14s), GET không lộ đáp án, nộp lần 1 được 40% (2/5, 2 câu bỏ trống) nên mastery SQL 0.4; nộp lần 2 đúng hết, mastery 0.7 (7/10, cộng dồn đúng); câu hỏi lạ trả 400; đề không tồn tại trả 404. Supervisor phân loại đúng 4/4 tin nhắn thật, kể cả câu đánh lừa "Kiểm tra giúp mình xem khóa ngoại là gì" (sang RAG). Lớp kiểm tra đã loại 1 câu có phương án "tất cả..." và vòng 2 sinh bù đủ.
- Dữ liệu quiz tạo trong lúc test đã được xoá (DB sạch cho demo).

### Task 5 — Study Planner Agent + `/api/chat` qua Supervisor (xong, 2026-10-27)
**Database**: `study_plans` (user_id, title, goal, summary, num_days, daily_minutes, start_date, end_date, deadline, focus_topics JSONB, status active/completed/archived) và `study_plan_items` (day_number, scheduled_date, position, topic, activity_type, title, description, duration_minutes, status pending/completed/skipped, completed_at). Đã tạo trên Supabase.

**Study Planner** (`app/services/study_planner_service.py`, tên hàm theo tool trong rule: `get_topic_mastery`, `create_study_plan`, `update_plan_progress`):
- Đọc mastery 5 chủ đề thẳng từ `user_topic_mastery`. Chủ đề chưa làm bài ghi "chưa có dữ liệu", không gán điểm giả và không tính là yếu. Chủ đề cần ưu tiên = mastery < 0.7, yếu nhất trước (tính bằng code, không để LLM tự chọn).
- LLM (Structured Output `GeneratedPlan{summary, tasks[day, topic, activity_type, title, description, duration_minutes]}`) nhận đúng số liệu thật + chủ đề ưu tiên + giới hạn phút/ngày.
- `validate_plan` (code): **tổng phút của từng ngày ≤ daily_minutes** (kiểm theo từng ngày, không theo trung bình); day trong 1..num_days; ngày nào cũng có nhiệm vụ; ≤ 4 nhiệm vụ/ngày; mỗi nhiệm vụ ≥ 5 phút; mọi chủ đề ưu tiên xuất hiện ít nhất 1 lần.
- Vi phạm → gửi lại danh sách lỗi cụ thể cho LLM sửa (tối đa 2 vòng). Vẫn sai → `PlanGenerationError`, **không lưu kế hoạch sai**.
- Mỗi người chỉ có 1 kế hoạch `active`: tạo kế hoạch mới thì kế hoạch active cũ chuyển `archived`. Kế hoạch tự chuyển `completed` khi không còn nhiệm vụ `pending`.
- Tham số ngoài phạm vi (num_days 1-30, daily_minutes 10-480, kế hoạch kết thúc sau `deadline`) bị từ chối trước khi gọi LLM.

**Supervisor**: thêm intent `study_planner`; classifier trích `num_days`, `daily_minutes` (đổi giờ sang phút), `goal`. **Không có thời gian rảnh mỗi ngày thì hỏi lại** (`clarification`), không tự đoán. Fallback từ khoá cũng nhận diện kế hoạch ("kế hoạch", "lịch học", "lộ trình"...) và trích "7 ngày", "1 tuần", "20 phút", "1,5 tiếng", "nửa tiếng".

**`POST /api/chat` đổi định dạng response** (breaking change so với Task 3, Frontend phải theo dạng mới):
```
{ "type": "rag_answer" | "quiz" | "study_plan" | "clarification" | "error",
  "intent": "rag_tutor" | "quiz_agent" | "study_planner",
  "message": "câu hiển thị ngay được trong khung chat",
  "rag_answer": {answer, has_enough_evidence, citations, sources} | null,
  "quiz": {quiz_set_id, title, topic, difficulty, question_count} | null,
  "study_plan": {plan_id, title, start_date, end_date, num_days, daily_minutes, focus_topics, item_count} | null }
```
Luôn trả HTTP 200; lỗi agent (dịch vụ AI không phản hồi...) là `type="error"` kèm `message`. Request giữ nguyên `{question, document_ids?, top_k?}`. Đã cập nhật `scripts/test_rag.py`, `scripts/evaluate_rag.py` theo dạng mới (evaluate còn đếm số câu bị Supervisor chuyển nhầm).

**API** (`app/routers/study_plans.py`): `POST /api/study-plans/generate` `{goal, num_days, daily_minutes, start_date?, deadline?}` (201, trả kế hoạch nhóm theo ngày kèm `total_minutes`), `GET /api/study-plans?status=` (mới nhất trước, kèm `progress`), `PATCH /api/study-plans/{id}/items/{item_id}` `{status}` (người khác/nhiệm vụ không thuộc kế hoạch → 404).

**Kiểm thử:**
- `pytest`: **106 test pass** (thêm 24 test Planner — trong đó 5 test riêng cho ràng buộc phút/ngày: đúng bằng giới hạn hợp lệ, vượt 1 phút bị chặn, kiểm theo từng ngày chứ không theo trung bình, báo mọi ngày vượt, 1 nhiệm vụ dài hơn giới hạn; vẫn sai sau 2 vòng thì không lưu — và 6 test endpoint `/api/chat` cho từng `type`).
- Chạy thật qua `/api/chat`: 3 yêu cầu tạo quiz → làm bài được SQL 40%, Giao dịch 33%, Mô hình quan hệ 100%; "Lập kế hoạch ôn tập cho mình" → hỏi lại số phút; "7 ngày, mỗi ngày 20 phút" → kế hoạch 14 nhiệm vụ, **cả 7 ngày đúng 20 phút**, ưu tiên Giao dịch + SQL (60 phút mỗi chủ đề), chủ đề chưa có dữ liệu được xếp bài quiz. Tạo kế hoạch mới → cũ chuyển `archived`; PATCH cập nhật tiến độ; deadline quá sớm → 422.
- Chạy lại `evaluate_rag.py` qua Supervisor: **chuyển nhầm 0/60**, Recall@5 90%, trích dẫn hợp lệ 100%, từ chối đúng 10/10, tỷ lệ trả lời 94% (trước 96%: RAG-47 bị từ chối ở lần chạy này — dao động của LLM, câu vẫn được chuyển đúng tới RAG).
- Dữ liệu quiz/kế hoạch/mastery tạo khi test đã xoá (DB sạch cho demo).
- Chi phí: mỗi tin nhắn `/api/chat` giờ tốn thêm 1 lượt gọi LLM để phân loại (~1s).

### Task 5.5 — Hoàn thiện backend cho Demo & UI (xong, 2026-10-27)
**Database** (đã tạo trên Supabase): `chat_sessions` (user_id, title = câu hỏi đầu, updated_at), `chat_messages` (role user/assistant, content, `type` + `payload` JSONB = toàn bộ ChatResponse để Frontend dựng lại trích dẫn/thẻ quiz/thẻ kế hoạch khi tải lại trang), `agent_runs` (user_id, session_id, message_id, intent, intent_source, agent_name, tools_called JSONB, duration_ms, status success/clarification/error, error_message, created_at) và **`profiles`** (user_id, display_name, daily_minutes, goal, frequent_mistakes JSONB).
- Thêm `profiles` (ngoài danh sách yêu cầu) vì `demo_cases.json` cảnh 5 hỏi "Tôi nên học gì trong ba ngày tới?" **không nói số phút**: Planner cần thời gian rảnh đã khai báo trong hồ sơ (đúng tool `get_user_availability` trong rule). Mỗi lần lập kế hoạch với số phút mới, hồ sơ được cập nhật.
- `agent_runs` **không có cột nội dung tin nhắn/prompt/payload** (có test kiểm tra). Lỗi ngoài dự kiến chỉ lưu tên lớp lỗi (vd. `RuntimeError`), không lưu thông điệp thô (có thể chứa chuỗi kết nối...).

**Ghi nhận tool thực sự được gọi** (`app/services/tracing.py`): `ContextVar` + `record_tool(name)` đặt trong service; `chat_service` bọc mỗi lượt bằng `tool_trace()`. Đã kiểm chứng tool ghi bên trong node LangGraph vẫn được thu đúng. Ví dụ chạy thật:
- RAG: `classify_intent, search_knowledge, answer_with_citations, validate_citations` (câu dưới ngưỡng chỉ có `classify_intent, search_knowledge`).
- Quiz: `classify_intent, search_knowledge ×4, generate_quiz, save_quiz`.
- Planner: `classify_intent, get_user_availability, get_topic_mastery, get_document_outline, generate_study_plan, validate_plan, create_study_plan`.

**Chat** (`app/services/chat_service.py`, `app/routers/chat.py`, `app/routers/agent_runs.py`):
- `POST /api/chat` nhận thêm `session_id` (không có thì tạo phiên mới); response thêm `session_id`, `message_id`; `intent` có thể null (lỗi trước khi phân loại xong). Câu hỏi được lưu + commit TRƯỚC khi chạy agent; trả lời + agent_run lưu sau. Lỗi ngoài dự kiến vẫn trả 200 `type=error` và vẫn ghi agent_run.
- **Hỏi lại nhiều lượt**: nếu tin trước của trợ lý là `clarification`, Supervisor nhận thêm ngữ cảnh (câu của người học + câu hỏi lại) → "Tạo cho mình một bài kiểm tra" → "chủ đề nào?" → "SQL, 3 câu thôi" tạo đúng đề SQL 3 câu. Không có ngữ cảnh này thì câu trả lời ngắn bị hiểu là câu hỏi kiến thức.
- `GET /api/chat/sessions` (kèm message_count, mới hoạt động trước), `GET /api/chat/sessions/{id}/messages` (theo thời gian, tin trợ lý kèm payload; phiên của người khác → 404), `GET /api/agent-runs?limit=20` (chỉ của user hiện tại, tối đa 100).
- Lỗi đã sửa khi chạy thật: (1) ORM chèn `agent_runs` trước `chat_messages` → vi phạm FK `message_id` (không có relationship nên SQLAlchemy không biết thứ tự) → flush tin nhắn trước. (2) Đồng hồ Windows độ phân giải thô làm câu hỏi và trả lời trùng timestamp → trả lời luôn được gán thời điểm sau câu hỏi ít nhất 1µs.

**Planner gắn nhiệm vụ với mục + trang tài liệu**:
- `get_document_outline`: dùng lại truy vấn chủ đề của Quiz Agent, **embed mọi truy vấn trong 1 lần gọi API** (`embed_queries`) rồi tra pgvector (`search_by_vector`, tách từ `search_knowledge`), giữ chunk vượt ngưỡng, gom theo (tài liệu, mục), lấy trang nhỏ nhất, tối đa 5 mục/chủ đề.
- Prompt kèm `<tai_lieu>` (mục + trang theo chủ đề) và `<loi_hay_gap>` (từ hồ sơ); yêu cầu tiêu đề nhiệm vụ ghi mục + "tr. N".
- `validate_plan` thêm kiểm tra: **số trang nhắc trong tiêu đề/mô tả phải có trong danh sách đã đưa cho LLM**, nếu không coi là bịa nguồn → gửi lại cho LLM sửa.
- Chạy thật cảnh 5 với hồ sơ HS01: kế hoạch 3 ngày × 20 phút, ưu tiên Giao dịch + SQL, nhiệm vụ như "5.1 Giao dịch, COMMIT và ROLLBACK (GT_Co_so_du_lieu, tr. 26)", "Kết hợp WHERE và HAVING (BT_SQL_Bai_tap_va_loi_giai, tr. 10)" — khớp lỗi hay gặp của HS01.

**Script `backend/scripts/seed_demo_profile.py`**:
- `--list` (5 hồ sơ), mặc định nạp **HS01** (SQL 60%, Mô hình quan hệ 90%, Giao dịch 50%, 20 phút/ngày), `--profile HS0x`, `--user-id`, `--reset`.
- Nạp `profiles` + mỗi lượt trong `attempt_history` thành 1 `quiz_set` "[Mẫu HS01-A1] ..." + 1 `quiz_attempt` (chỉ là bản ghi lịch sử, không có câu hỏi chi tiết vì dữ liệu gốc chỉ có số câu đúng/tổng) + `user_topic_mastery` cộng dồn bằng đúng `merge_mastery` của app. Kiểm tra mastery tính ra khớp `topic_scores` trước khi ghi.
- Không có `--reset` mà user đã có dữ liệu học tập → dừng (tránh cộng dồn 2 lần). `--reset` xoá chat, agent_runs, kế hoạch, quiz/lần làm bài, mastery, profile — **giữ nguyên tài liệu đã nạp**.
- Không có file `learner_profiles.json` → dùng hồ sơ HS01 dựng sẵn trong script (có test bảo đảm trùng dữ liệu file).

**Kiểm thử:** `pytest` **158 test pass** (+52: tracing qua LangGraph, chat_service, API lịch sử/agent-runs, chống bịa trang, outline, ngữ cảnh hỏi lại, thời gian rảnh từ hồ sơ, seed trên cả 5 hồ sơ thật).

**Trạng thái DB sau Task 5.5 (sẵn sàng demo):** 3 tài liệu corpus (54 chunk) + hồ sơ HS01 đã seed; không có phiên chat/kế hoạch thừa.
**Quy trình trước giờ demo:** `python scripts/seed_demo_profile.py --reset` (nếu chưa có tài liệu: chạy `scripts/test_rag.py` trước). Sau khi chạy `evaluate_rag.py` cũng phải chạy lại lệnh này (đánh giá tạo 60 phiên chat).

### Đánh giá bằng bộ mock data CSDL (2026-10-27)
Dữ liệu: `StudyMate_AI_Bo_mock_data_CSDL/` (user chuẩn bị) — corpus 3 PDF (`GT_Co_so_du_lieu`, `BT_SQL_Bai_tap_va_loi_giai`, `CD_Giao_dich_va_ACID`, nạp từ `sample_docs/`), `data/rag_eval.json` (50 câu có nguồn chuẩn), `data/negative_eval.json` (10 câu cần từ chối).

Script: `backend/scripts/test_rag.py` (nạp corpus + 2 câu kiểm tra nhanh) và `backend/scripts/evaluate_rag.py` (60 câu, lưu tiến độ sau mỗi câu vào `scripts/output/` — đã gitignore; `--reset` để chạy lại từ đầu):
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

## Việc còn thiếu / cần làm tiếp

- Bảng `profiles` đã có (Task 5.5) nhưng chưa có FK từ `documents.owner_id` / các bảng khác sang `profiles`, và chưa tự tạo profile khi người dùng đăng ký.
- OCR cho PDF scan (spec ghi rõ: để giai đoạn sau).
- Hỏi lại chỉ nhớ 1 lượt (lượt trước là clarification); hội thoại nhiều lượt tổng quát (hỏi tiếp "giải thích thêm ý 2") chưa hỗ trợ — RAG vẫn trả lời từng câu độc lập.
- Đề "[Mẫu]" do seed tạo không có câu hỏi chi tiết: mở `GET /api/quizzes/{id}` của chúng sẽ thấy danh sách câu rỗng (Frontend nên ẩn nút "Làm bài" với các đề này).
- Frontend — chưa khởi tạo.
- Đánh giá chất lượng quiz do AI sinh (spec XII.2: >= 90% câu rõ ràng, có căn cứ) — chưa có script; có thể đối chiếu với `quiz_reference.json`.
