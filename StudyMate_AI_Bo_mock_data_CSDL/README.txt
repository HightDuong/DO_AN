BỘ MOCK DATA STUDYMATE AI - CƠ SỞ DỮ LIỆU
Phiên bản 1.0, ngày 27/10/2026. Mọi dữ liệu người học đều giả lập.

1. Nạp vào RAG: đúng 3 PDF trong thư mục corpus/.
2. KHÔNG NẠP vào RAG: PDF trong evaluation/ hoặc bất kỳ file data/ nào.
3. Đọc evaluation/KT_Demo_RAG_Quiz_Ho_so.pdf để chạy 6 cảnh demo.
4. data/rag_eval.json: 50 câu có nguồn, đáp án và trích dẫn nguyên văn.
   data/negative_eval.json: 10 câu cần từ chối do thiếu căn cứ.
   data/quiz_reference.json: 25 quiz mẫu, mỗi câu 4 lựa chọn.
   data/learner_profiles.json: 5 hồ sơ, điểm và lịch sử giả lập.
5. Chạy data/schema_and_seed.sql trong CSDL thử nghiệm TRỐNG.
   Cú pháp hướng PostgreSQL; không ghi đè lên CSDL đang dùng.
   data/transaction_setup.sql tạo bảng riêng cho chuyên đề giao dịch.
6. Thay document_code GT/BT/CD bằng document_id thật của API sau upload.
   section_id ổn định; chunk_id phải lấy từ pipeline thật.
7. pdf_page tính từ 1 và bao gồm bìa.
8. Dùng dev để hiệu chỉnh; chốt cấu hình trước khi chấm test.
9. validation_report.json mô tả xác minh cục bộ và giới hạn. Chưa có
   kết quả RAG, ngưỡng 0.65 hoặc kiểm thử hai phiên PostgreSQL thực tế.

LƯU Ý: Đây là bộ fixture trung lập, chưa phải file import theo API cụ thể
của dự án vì toàn văn spec.md và mã nguồn chưa được cung cấp trong yêu cầu.
