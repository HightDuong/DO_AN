/** Phân mức thành thạo theo điểm (0..1) để tô màu thanh tiến độ và gắn nhãn. */
export type MasteryLevel = "strong" | "fair" | "weak" | "none";

export function masteryLevel(score: number | null | undefined): MasteryLevel {
  if (score === null || score === undefined) return "none";
  if (score >= 0.8) return "strong";
  if (score >= 0.5) return "fair";
  return "weak";
}

export const MASTERY_STYLE: Record<MasteryLevel, { bar: string; text: string; label: string }> = {
  strong: { bar: "bg-emerald-500", text: "text-emerald-600", label: "Vững" },
  fair: { bar: "bg-amber-500", text: "text-amber-600", label: "Khá" },
  weak: { bar: "bg-rose-500", text: "text-rose-600", label: "Cần ôn tập" },
  none: { bar: "bg-slate-300", text: "text-slate-400", label: "Chưa có dữ liệu" },
};

export function percent(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : `${Math.round(score * 100)}%`;
}
