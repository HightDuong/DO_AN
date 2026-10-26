# FRONTEND & UI/UX RULES (GAMIFIED MINIMALISM)

## 1. Triết lý thiết kế: Gamified Minimalism
- **Minimalism (Tối giản):** Bố cục thoáng, nhiều khoảng trắng (whitespace), sử dụng font chữ không chân hiện đại (Inter hoặc Plus Jakarta Sans), hạn chế đường viền rườm rà, ưu tiên dùng đổ bóng nhẹ (`shadow-sm`) và bo góc lớn (`rounded-xl`, `rounded-2xl`).
- **Gamification (Trò chơi hóa):** Biến việc học thành trải nghiệm đạt thành tựu (tương tự Duolingo hoặc Notion):
  - Hiển thị thanh kinh nghiệm (Progress Bar) cho mức độ thành thạo từng chủ đề (`user_topic_mastery`).
  - Dùng hệ thống Badge/Tag màu sắc trực quan cho độ khó câu hỏi và trạng thái hoàn thành.
  - Chuỗi ngày học liên tiếp (Streak) và hiệu ứng chúc mừng nhẹ nhàng khi hoàn thành bài Quiz hoặc nhiệm vụ trong ngày.

## 2. Thư viện & Component
- Sử dụng **Tailwind CSS** kết hợp **shadcn/ui** và bộ icon **Lucide React**.
- Màu sắc chủ đạo: Nền sáng sạch sẽ (`bg-slate-50`), màu nhấn (Accent) tạo cảm giác năng lượng và tập trung (như Indigo `indigo-600`, Emerald `emerald-500` cho đáp án đúng/hoàn thành, Amber `amber-500` cho điểm thưởng/cảnh báo ôn tập).