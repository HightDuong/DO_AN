# StudyMate AI — Frontend

Next.js 16 (App Router, TypeScript, Tailwind CSS 4) + Lucide React. Gọi FastAPI backend ở `NEXT_PUBLIC_API_URL`.

## Chạy

```bash
# 1. Backend (terminal khác): cd backend && uvicorn app.main:app --reload --port 8000
# 2. Frontend:
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                  # http://localhost:3000
```

## Kiểm tra

```bash
npm run typecheck   # tsc --noEmit
npm run build
```

## Kiểu dữ liệu API

`src/lib/api-types.ts` được **sinh tự động** từ OpenAPI của backend — không sửa tay. Khi đổi schema backend:

```bash
cd backend && python scripts/export_openapi.py   # ghi frontend/openapi.json
cd ../frontend && npm run gen:api                 # sinh lại src/lib/api-types.ts
```

`src/lib/api.ts` đặt tên ngắn cho các kiểu đó và chứa toàn bộ hàm gọi API.

## Cấu trúc

- `src/app/` — các trang: `/` Dashboard, `/documents` Knowledge Library, `/chat` AI Tutor, `/quizzes`, `/study-plans`
- `src/components/` — layout (`app-shell`), ngăn kéo Nhật ký Agent, component UI (`ui.tsx`), hiển thị tin nhắn chat
- `src/lib/` — client API, hook `useApi`, định dạng ngày giờ, màu theo mức thành thạo
