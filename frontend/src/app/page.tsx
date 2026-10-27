"use client";

import {
  BookOpen,
  CalendarCheck,
  CheckCircle2,
  Circle,
  Flame,
  History,
  MinusCircle,
  Sparkles,
  Target,
  Trophy,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Badge, Card, CardHeader, EmptyState, ErrorState, LoadingState, PageHeader, ProgressBar } from "@/components/ui";
import { api, type DocumentOut, type LearningSummary, type StudyPlan, type StudyPlanDay, type TopicMastery } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, formatWeekday, todayIso } from "@/lib/format";
import { MASTERY_STYLE, masteryLevel, percent } from "@/lib/mastery";
import { useApi } from "@/lib/use-api";

type DashboardData = { summary: LearningSummary; documents: DocumentOut[]; plan: StudyPlan | null };

async function loadDashboard(): Promise<DashboardData> {
  const [summary, documents, activePlans] = await Promise.all([
    api.getLearningSummary(),
    api.listDocuments(),
    api.listStudyPlans("active"),
  ]);
  return { summary, documents, plan: activePlans[0] ?? null };
}

export default function DashboardPage() {
  const { data, error, loading, reload } = useApi(loadDashboard);

  return (
    <>
      <PageHeader title="Chào mừng trở lại 👋" description="Tiến độ ôn tập môn Cơ sở dữ liệu của bạn" />
      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && <LoadingState />}
      {data && <Dashboard {...data} />}
    </>
  );
}

function Dashboard({ summary, documents, plan }: DashboardData) {
  const indexed = documents.filter((d) => d.status === "indexed");
  const pages = indexed.reduce((sum, d) => sum + (d.page_count ?? 0), 0);
  const streak = studyStreak(summary, plan);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={<BookOpen className="h-5 w-5" />}
          tone="bg-indigo-50 text-indigo-600"
          label="Tài liệu đã nạp"
          value={String(indexed.length)}
          hint={pages ? `${pages} trang giáo trình` : "Chưa có tài liệu"}
        />
        <StatCard
          icon={<Trophy className="h-5 w-5" />}
          tone="bg-violet-50 text-violet-600"
          label="Bài quiz đã làm"
          value={String(summary.attempts_count)}
          hint={`${summary.quizzes_created} bộ đề`}
        />
        <StatCard
          icon={<Target className="h-5 w-5" />}
          tone="bg-emerald-50 text-emerald-600"
          label="Điểm gần nhất"
          value={summary.latest_score === null ? "—" : `${Math.round(summary.latest_score)}%`}
          hint={summary.average_score === null ? "Chưa làm bài" : `Trung bình ${Math.round(summary.average_score)}%`}
        />
        <StatCard
          icon={<Flame className="h-5 w-5" />}
          tone="bg-amber-50 text-amber-600"
          label="Chuỗi ngày học"
          value={`${streak} ngày`}
          hint={streak ? "Giữ lửa nhé!" : "Học hôm nay để bắt đầu chuỗi"}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <MasteryCard mastery={summary.topic_mastery} weakTopics={summary.weak_topics} className="lg:col-span-3" />
        <TodayPlanCard plan={plan} className="lg:col-span-2" />
      </div>

      <RecentAttempts summary={summary} />
    </div>
  );
}

function StatCard({ icon, tone, label, value, hint }: { icon: ReactNode; tone: string; label: string; value: string; hint: string }) {
  return (
    <Card className="p-5">
      <span className={cn("mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl", tone)}>{icon}</span>
      <p className="text-xs font-medium text-slate-400">{label}</p>
      <p className="mt-0.5 text-2xl font-bold text-slate-900">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{hint}</p>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Mức độ thành thạo
// ---------------------------------------------------------------------------

function MasteryCard({ mastery, weakTopics, className }: { mastery: TopicMastery[]; weakTopics: string[]; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader title="Mức độ thành thạo theo chủ đề" icon={<Sparkles className="h-4 w-4 text-indigo-500" />} />
      <ul className="space-y-5 p-5">
        {mastery.map((m) => (
          <MasteryRow key={m.topic} mastery={m} />
        ))}
      </ul>
      {weakTopics.length > 0 && (
        <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
          Study Planner đang ưu tiên (dưới 70%): <span className="font-medium text-slate-700">{weakTopics.join(", ")}</span>
        </p>
      )}
    </Card>
  );
}

function MasteryRow({ mastery }: { mastery: TopicMastery }) {
  const level = masteryLevel(mastery.mastery_score);
  const style = MASTERY_STYLE[level];
  return (
    <li>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-medium text-slate-700">
          {mastery.topic}
          {level === "weak" && <Badge tone="rose">Cần ôn tập</Badge>}
        </span>
        <span className="flex items-baseline gap-2">
          {mastery.total_count > 0 && (
            <span className="text-xs text-slate-400">
              {mastery.correct_count}/{mastery.total_count} câu đúng
            </span>
          )}
          <span className={cn("text-sm font-semibold", style.text)}>{percent(mastery.mastery_score)}</span>
        </span>
      </div>
      <ProgressBar value={mastery.mastery_score ?? 0} barClassName={style.bar} />
      {level === "none" && <p className="mt-1 text-xs text-slate-400">Chưa làm bài kiểm tra nào ở chủ đề này</p>}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Kế hoạch hôm nay
// ---------------------------------------------------------------------------

function pickDay(plan: StudyPlan): { day: StudyPlanDay | null; note: string | null } {
  const today = todayIso();
  const exact = plan.days.find((d) => d.date === today);
  if (exact) return { day: exact, note: null };
  if (today < plan.start_date) return { day: plan.days[0] ?? null, note: `Kế hoạch bắt đầu ngày ${formatDate(plan.start_date)}` };
  return { day: null, note: `Kế hoạch đã kết thúc ngày ${formatDate(plan.end_date)}` };
}

function TodayPlanCard({ plan, className }: { plan: StudyPlan | null; className?: string }) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader
        title="Kế hoạch hôm nay"
        icon={<CalendarCheck className="h-4 w-4 text-sky-500" />}
        action={
          plan && (
            <Link href="/study-plans" className="text-xs font-medium text-indigo-600 hover:underline">
              Xem đầy đủ
            </Link>
          )
        }
      />
      {plan ? <TodayPlan plan={plan} /> : (
        <EmptyState
          icon={<CalendarCheck className="h-8 w-8" />}
          title="Chưa có kế hoạch học tập"
          hint={
            <>
              Vào <Link href="/chat" className="text-indigo-600 hover:underline">AI Tutor</Link> và hỏi
              “Tôi nên học gì trong ba ngày tới?”
            </>
          }
        />
      )}
    </Card>
  );
}

function TodayPlan({ plan }: { plan: StudyPlan }) {
  const { day, note } = pickDay(plan);
  return (
    <div className="flex flex-1 flex-col p-5">
      {note && <p className="mb-3 text-xs text-amber-600">{note}</p>}
      {day && (
        <>
          <p className="mb-3 text-xs text-slate-400">
            Ngày {day.day_number}/{plan.num_days} · {formatWeekday(day.date)} · {day.total_minutes}/{plan.daily_minutes} phút
          </p>
          <ul className="space-y-2.5">
            {day.items.map((item) => (
              <li key={item.id} className="flex items-start gap-2.5">
                <ItemStatusIcon status={item.status} />
                <div className="min-w-0 flex-1">
                  <p className={cn("text-sm text-slate-700", item.status !== "pending" && "text-slate-400 line-through")}>
                    {item.title}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                    <Badge tone="slate">{item.topic}</Badge>
                    {item.activity_type} · {item.duration_minutes} phút
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="mt-auto pt-5">
        <div className="mb-1.5 flex justify-between text-xs text-slate-400">
          <span>Tiến độ cả kế hoạch</span>
          <span className="font-medium text-slate-600">{Math.round(plan.progress * 100)}%</span>
        </div>
        <ProgressBar value={plan.progress} barClassName="bg-sky-500" />
      </div>
    </div>
  );
}

function ItemStatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />;
  if (status === "skipped") return <MinusCircle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />;
  return <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />;
}

// ---------------------------------------------------------------------------
// Lần làm bài gần đây
// ---------------------------------------------------------------------------

function RecentAttempts({ summary }: { summary: LearningSummary }) {
  const attempts = summary.recent_attempts.slice(0, 5);
  return (
    <Card>
      <CardHeader title="Bài làm gần đây" icon={<History className="h-4 w-4 text-violet-500" />} />
      {attempts.length === 0 ? (
        <EmptyState title="Chưa có bài làm nào" hint="Tạo quiz trong AI Tutor, ví dụ “Tạo 5 câu trắc nghiệm SQL”." />
      ) : (
        <ul className="divide-y divide-slate-50 px-5 pb-2 pt-3">
          {attempts.map((a) => {
            const style = MASTERY_STYLE[masteryLevel(a.score / 100)];
            return (
              <li key={a.attempt_id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-700">{a.quiz_title}</p>
                  <p className="text-xs text-slate-400">
                    {a.topic} · {formatDate(a.submitted_at)}
                  </p>
                </div>
                <span className="text-right">
                  <span className={cn("block text-sm font-semibold", style.text)}>{Math.round(a.score)}%</span>
                  <span className="text-xs text-slate-400">
                    {a.correct_count}/{a.total_questions} câu
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Chuỗi ngày học: số ngày liên tiếp (tính tới hôm nay hoặc hôm qua) có làm quiz hoặc xong nhiệm vụ.
// ---------------------------------------------------------------------------

function studyStreak(summary: LearningSummary, plan: StudyPlan | null): number {
  const days = new Set<string>();
  const toLocalDay = (iso: string) => {
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  summary.recent_attempts.forEach((a) => days.add(toLocalDay(a.submitted_at)));
  plan?.days.forEach((d) => d.items.forEach((i) => i.completed_at && days.add(toLocalDay(i.completed_at))));

  const cursor = new Date();
  const key = () => toLocalDay(cursor.toISOString());
  if (!days.has(key())) cursor.setDate(cursor.getDate() - 1); // chưa học hôm nay: tính từ hôm qua
  let streak = 0;
  while (days.has(key())) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return streak;
}
