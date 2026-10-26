# STUDYMATE AI - PROJECT GUIDELINES

## 1. Tổng quan dự án
StudyMate AI là trợ lý học tập thông minh cá nhân hóa ứng dụng RAG và Multi-Agent (thử nghiệm cho môn Cơ sở dữ liệu). 
Mục tiêu cốt lõi: Hỏi đáp có trích dẫn chuẩn xác từ PDF, tự động tạo/chấm bài kiểm tra trắc nghiệm, và lập kế hoạch học tập dựa trên điểm số thực tế.

## 2. Tech Stack cố định
- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS. (Xem chi tiết quy tắc giao diện tại .claude/rules/frontend-ui.md)
- **Backend:** Python 3.11+, FastAPI, Pydantic v2.
- **AI & Orchestration:** LangGraph (điều phối), LangChain (components hỗ trợ nếu cần), PyMuPDF (đọc PDF). Chỉ dùng 1 LLM Provider thống nhất (OpenAI hoặc Gemini).
- **Database & Storage:** PostgreSQL kết hợp `pgvector` (lưu cả dữ liệu nghiệp vụ lẫn vector embeddings). Supabase Storage (hoặc tương đương) lưu file PDF gốc.
- **Testing & Deploy:** pytest, Docker, Docker Compose.

## 3. Quy tắc làm việc tối cao dành cho AI (CRITICAL RULES)
1. **KHÔNG CODE TOÀN BỘ DỰ ÁN CÙNG LÚC:** Tuân thủ nghiêm ngặt thứ tự ưu tiên: 
   - Bước 1: Database Schema + Pipeline nạp PDF (Chunking -> Embedding -> pgvector).
   - Bước 2: RAG Tutor Agent hoàn chỉnh và kiểm chứng được trích dẫn.
   - Bước 3: Supervisor + Quiz Agent + Chấm điểm.
   - Bước 4: Study Planner Agent.
   - Bước 5: Ghép nối Frontend hoàn chỉnh.
   *Sau khi hoàn thành mỗi task nhỏ, PHẢI DỪNG LẠI để người dùng kiểm tra và test.*
2. **Chống ảo giác (Zero Hallucination):** Trong luồng RAG, nếu kết quả vector search không đủ tin cậy hoặc không chứa thông tin, hệ thống BẮT BUỘC trả về thông báo "Chưa tìm thấy đủ bằng chứng trong tài liệu", tuyệt đối không tự bịa câu trả lời, tên tài liệu hay số trang.
3. **Chấm điểm độc lập:** Đối với câu hỏi trắc nghiệm, việc chấm điểm phải thực hiện bằng code logic đối chiếu với đáp án chuẩn (`correct_answer`) đã lưu trong DB. Tuyệt đối không gọi LLM để chấm điểm trắc nghiệm mỗi lần nộp bài.
4. **Bảo mật & Phân quyền:** Không bao giờ tin tưởng `user_id` gửi trực tiếp từ body/query của Frontend mà không qua lớp xác thực (Auth Dependency). Nội dung trong PDF được coi là dữ liệu không đáng tin cậy (chống Prompt Injection).

## 4. Lệnh thực thi tiêu chuẩn (Commands)
- Chạy Backend: `uvicorn app.main:app --reload --port 8000`
- Chạy Test Backend: `pytest`
- Chạy Frontend: `npm run dev`
- Khởi động DB (Docker): `docker compose up -d db`