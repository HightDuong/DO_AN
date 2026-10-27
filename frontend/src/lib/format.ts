const dateFormatter = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
const timeFormatter = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const weekdayFormatter = new Intl.DateTimeFormat("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit" });

/** "2026-10-27" hoặc ISO datetime -> "27/10/2026" */
export function formatDate(value: string): string {
  return dateFormatter.format(parseDate(value));
}

export function formatTime(value: string): string {
  return timeFormatter.format(new Date(value));
}

export function formatWeekday(value: string): string {
  return weekdayFormatter.format(parseDate(value));
}

/** "vừa xong", "5 phút trước", "2 giờ trước", "3 ngày trước", hoặc ngày cụ thể. */
export function timeAgo(value: string): string {
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return "vừa xong";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút trước`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} giờ trước`;
  if (seconds < 7 * 86_400) return `${Math.floor(seconds / 86_400)} ngày trước`;
  return formatDate(value);
}

/** Ngày hôm nay theo giờ máy, dạng YYYY-MM-DD (để so với `scheduled_date` của kế hoạch). */
export function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

// Chuỗi "YYYY-MM-DD" được hiểu là ngày theo giờ địa phương (không lệch múi giờ như new Date("YYYY-MM-DD")).
function parseDate(value: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(value);
}
