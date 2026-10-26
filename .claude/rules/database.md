# DATABASE SCHEMA & STORAGE RULES

## 1. Nguyên tắc lưu trữ
- Sử dụng duy nhất **PostgreSQL + extension `vector` (pgvector)**. Không cài đặt thêm vector DB rời bên ngoài (như Qdrant hay Milvus) trong giai đoạn MVP.
- File PDF gốc lưu trên Object Storage, trong DB chỉ lưu đường dẫn (`storage_path`).

## 2. Cấu trúc các bảng cốt lõi phải tuân thủ
- `profiles`: Thông tin hồ sơ người học liên kết tài khoản xác thực.
- `documents`: `id`, `owner_id`, `title`, `source_url`, `storage_path`, `license`, `status` (ENUM: `uploaded`, `processing`, `indexed`, `failed`), `created_at`.
- `document_chunks`: `id`, `document_id` (FK), `chunk_index`, `page_number`, `section`, `content`, `embedding` (vector), `created_at`.
- `quiz_sets`: Thông tin bộ đề (`creator_id`, `title`, `topic`, `question_count`, `difficulty`, `created_at`).
- `quiz_questions`: Nội dung câu hỏi, mảng lựa chọn (JSONB), đáp án chuẩn, lời giải thích, độ khó.
- `quiz_question_sources`: Bảng trung gian (Many-to-Many) nối `quiz_questions` và `document_chunks` để truy vết nguồn tạo câu hỏi. Không lưu nguồn dạng chuỗi text tự do.
- `quiz_attempts` & `quiz_responses`: Lưu lịch sử làm bài và chi tiết từng câu trả lời của học viên.
- `user_topic_mastery`: Lưu mức độ thành thạo theo từng chủ đề (`user_id`, `topic`, `mastery_score`, `attempts_count`).
- `study_plans` & `study_plan_items`: Lưu kế hoạch học tập tổng và các nhiệm vụ chi tiết theo từng ngày (thời lượng, chủ đề, trạng thái hoàn thành).
- `chat_sessions`, `chat_messages`, và `agent_runs` (log thực thi của LangGraph, tuyệt đối không lưu API key vào đây).