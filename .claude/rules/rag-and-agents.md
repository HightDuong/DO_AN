# RAG PIPELINE & MULTI-AGENT ORCHESTRATION RULES

## 1. Thông số RAG Pipeline khởi điểm
- **Extractor:** Dùng `PyMuPDF` (`fitz`) để lấy văn bản kèm chính xác `page_number`.
- **Chunking:** Kích thước `500 - 800 tokens`, độ gối (`chunk_overlap`) `80 - 120 tokens`. Ưu tiên cắt theo cấu trúc đoạn và tiêu đề.
- **Retrieval:** Lấy `top 4 - 6` chunks có độ tương đồng cao nhất. Phải truyền kèm filter `owner_id` hoặc quyền truy cập tài liệu hợp lệ.

## 2. Kiến trúc LangGraph Workflow
Không để các Agent tự gọi nhau tự do tạo vòng lặp vô hạn. Mọi luồng đi qua **Supervisor** và các Node xác định:
- Các Node chính: `classify_intent`, `retrieve_context`, `answer_with_citations`, `generate_quiz`, `grade_attempt`, `load_learning_profile`, `generate_study_plan`, `validate_output`, `save_result`.
- Phải cài đặt `timeout` và giới hạn số lần retry (`max_retries = 2`) cho các node gọi LLM.

## 3. Quyền hạn và Công cụ (Tools) của từng Agent
1. **RAG Tutor Agent:**
   - Tools: `search_knowledge`, `get_document_metadata`, `validate_citations`.
   - Bắt buộc kiểm tra nguồn trích dẫn có thực sự nằm trong các chunk vừa truy xuất hay không trước khi trả về.
2. **Quiz Agent:**
   - Tools: `search_knowledge`, `generate_quiz`, `save_quiz`, `grade_attempt`, `update_topic_mastery`.
   - Ưu tiên sinh câu hỏi trắc nghiệm 1 đáp án đúng (MCQ) sử dụng Structured Outputs (Pydantic schema).
3. **Study Planner Agent:**
   - Tools: `get_learning_summary`, `get_topic_mastery`, `get_user_availability`, `create_study_plan`, `update_plan_progress`.
   - **Ràng buộc cứng:** Phải đọc điểm số thực tế từ DB (không tự suy đoán). Tổng thời lượng các hoạt động trong 1 ngày KHÔNG ĐƯỢC VƯỢT QUÁ thời gian rảnh mỗi ngày mà người học cung cấp.