"use client";

import {
  AlertTriangle,
  ArrowRight,
  BookMarked,
  CalendarCheck,
  ChevronDown,
  FileSearch,
  HelpCircle,
  SearchX,
  Trophy,
} from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { Markdown } from "@/components/chat/markdown";
import { Badge } from "@/components/ui";
import type { ChatResponse, Citation, QuizCreated, RagAnswer, StudyPlanCreated } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";

/** Hiển thị tin nhắn của trợ lý theo `type` của ChatResponse. */
export function AssistantMessage({ response }: { response: ChatResponse }) {
  switch (response.type) {
    case "rag_answer":
      return response.rag_answer ? <RagAnswerView rag={response.rag_answer} /> : <Bubble>{response.message}</Bubble>;
    case "quiz":
      return (
        <div className="space-y-3">
          <Bubble>{response.message}</Bubble>
          {response.quiz && <QuizCard quiz={response.quiz} />}
        </div>
      );
    case "study_plan":
      return (
        <div className="space-y-3">
          <Bubble>{response.message}</Bubble>
          {response.study_plan && <PlanCard plan={response.study_plan} />}
        </div>
      );
    case "clarification":
      return (
        <Bubble className="border-indigo-100 bg-indigo-50/60">
          <span className="flex items-start gap-2">
            <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
            <span>{response.message}</span>
          </span>
        </Bubble>
      );
    default:
      return (
        <Bubble className="border-rose-100 bg-rose-50 text-rose-700">
          <span className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{response.message}</span>
          </span>
        </Bubble>
      );
  }
}

function Bubble({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-2xl rounded-tl-md border border-slate-100 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm", className)}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RAG: câu trả lời + thẻ trích dẫn, hoặc thông báo thiếu căn cứ
// ---------------------------------------------------------------------------

function RagAnswerView({ rag }: { rag: RagAnswer }) {
  if (!rag.has_enough_evidence) {
    return (
      <div className="space-y-2">
        <div className="flex items-start gap-3 rounded-2xl rounded-tl-md border border-amber-200 bg-amber-50 px-4 py-3">
          <SearchX className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <div className="text-sm">
            <p className="font-semibold text-amber-800">Chưa tìm thấy đủ căn cứ trong giáo trình</p>
            <p className="mt-0.5 text-amber-700">
              StudyMate chỉ trả lời khi tài liệu có bằng chứng rõ ràng, nên không đưa ra câu trả lời đoán mò. Bạn có thể
              nạp thêm tài liệu liên quan hoặc hỏi trong phạm vi giáo trình.
            </p>
          </div>
        </div>
        <RetrievedSources rag={rag} />
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <Bubble>
        <Markdown text={rag.answer} />
      </Bubble>
      {rag.citations.length > 0 && <CitationList citations={rag.citations} />}
      <RetrievedSources rag={rag} />
    </div>
  );
}

function citationLabel(c: Citation): string {
  const parts = [c.document_title];
  if (c.page_number !== null) parts.push(`Trang ${c.page_number}`);
  if (c.section) parts.push(`Mục ${c.section.split(" > ").pop()}`);
  return parts.join(" · ");
}

function CitationList({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
        <BookMarked className="h-3.5 w-3.5" />
        Nguồn trích dẫn ({citations.length}) — bấm để xem nguyên văn
      </p>
      <div className="flex flex-wrap gap-2">
        {citations.map((c, i) => (
          <button
            key={i}
            onClick={() => setOpen(open === i ? null : i)}
            aria-expanded={open === i}
            className={cn(
              "inline-flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              open === i
                ? "border-indigo-300 bg-indigo-600 text-white"
                : "border-indigo-100 bg-indigo-50 text-indigo-700 hover:border-indigo-300",
            )}
          >
            <span className="truncate">[{citationLabel(c)}]</span>
            <ChevronDown className={cn("h-3 w-3 shrink-0 transition-transform", open === i && "rotate-180")} />
          </button>
        ))}
      </div>
      {open !== null && citations[open] && (
        <blockquote className="rounded-xl border-l-4 border-indigo-400 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
          <p className="italic">“{citations[open].quote}”</p>
          <footer className="mt-2 text-xs not-italic text-slate-400">— {citationLabel(citations[open])}</footer>
        </blockquote>
      )}
    </div>
  );
}

/** Các đoạn hệ thống đã truy xuất (kèm độ tương đồng) — giúp kiểm chứng khi demo. */
function RetrievedSources({ rag }: { rag: RagAnswer }) {
  if (rag.sources.length === 0) return null;
  return (
    <details className="group text-xs text-slate-500">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 hover:text-slate-700">
        <FileSearch className="h-3.5 w-3.5" />
        Đoạn tài liệu đã truy xuất ({rag.sources.length})
        <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />
      </summary>
      <ul className="mt-2 space-y-1.5">
        {rag.sources.map((s) => (
          <li key={s.chunk_id} className="rounded-lg bg-slate-50 px-3 py-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-medium text-slate-600">{s.document_title}</span>
              {s.page_number !== null && <span>· tr. {s.page_number}</span>}
              <Badge tone={s.used_as_context ? "emerald" : "slate"} className="ml-auto">
                {s.used_as_context ? "Đưa vào ngữ cảnh" : "Dưới ngưỡng"} · {s.similarity.toFixed(2)}
              </Badge>
            </div>
            <p className="mt-1 line-clamp-2 text-slate-400">{s.preview}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Thẻ hành động: quiz đã tạo / kế hoạch đã lập
// ---------------------------------------------------------------------------

function ActionCard({
  icon,
  tone,
  title,
  meta,
  href,
  cta,
}: {
  icon: ReactNode;
  tone: string;
  title: string;
  meta: ReactNode;
  href: string;
  cta: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
      <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl", tone)}>{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-slate-800">{title}</p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">{meta}</div>
      </div>
      <Link
        href={href}
        className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
      >
        {cta}
        <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

function QuizCard({ quiz }: { quiz: QuizCreated }) {
  return (
    <ActionCard
      icon={<Trophy className="h-5 w-5" />}
      tone="bg-violet-50 text-violet-600"
      title={quiz.title}
      meta={
        <>
          <Badge tone="violet">{quiz.topic}</Badge>
          <Badge tone={quiz.difficulty === "Vận dụng" ? "amber" : "emerald"}>{quiz.difficulty}</Badge>
          <span>{quiz.question_count} câu trắc nghiệm</span>
        </>
      }
      href={`/quizzes?quiz=${quiz.quiz_set_id}`}
      cta="Làm bài ngay"
    />
  );
}

function PlanCard({ plan }: { plan: StudyPlanCreated }) {
  return (
    <ActionCard
      icon={<CalendarCheck className="h-5 w-5" />}
      tone="bg-sky-50 text-sky-600"
      title={plan.title}
      meta={
        <>
          <span>
            {formatDate(plan.start_date)} – {formatDate(plan.end_date)} · {plan.item_count} nhiệm vụ
          </span>
          {plan.focus_topics.map((t) => (
            <Badge key={t} tone="rose">
              {t}
            </Badge>
          ))}
        </>
      }
      href="/study-plans"
      cta="Xem kế hoạch"
    />
  );
}
