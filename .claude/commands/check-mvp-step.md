Hãy kiểm tra toàn bộ mã nguồn hiện tại của dự án và đối chiếu với thứ tự ưu tiên triển khai MVP của StudyMate AI:
1. Đã có Docker Compose cho PostgreSQL + pgvector và các bảng DB cốt lõi chưa?
2. Pipeline nạp PDF -> Chunking -> Embedding -> Lưu DB đã chạy ổn định chưa?
3. RAG Tutor Agent đã trả lời kèm trích dẫn và biết từ chối khi thiếu dữ kiện chưa?
4. Supervisor và Quiz Agent (tạo đề + chấm điểm bằng đáp án chuẩn) đã hoạt động chưa?
5. Study Planner Agent đã tạo được lịch học dựa trên bảng `user_topic_mastery` chưa?

Báo cáo ngắn gọn trạng thái từng mục (Đã xong / Đang làm / Chưa làm) và đề xuất **1 task nhỏ duy nhất tiếp theo** tôi nên yêu cầu bạn code. Không tự ý viết code mới khi chạy lệnh này.