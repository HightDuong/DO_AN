"use client";

import { Activity, ArrowRight, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge, Button, EmptyState, ErrorState, LoadingState, type BadgeTone } from "@/components/ui";
import { api, type AgentRun } from "@/lib/api";
import { formatDuration, formatTime } from "@/lib/format";
import { errorMessage } from "@/lib/use-api";

const AGENT: Record<string, { label: string; tone: BadgeTone }> = {
  rag_tutor: { label: "RAG Tutor", tone: "indigo" },
  quiz_agent: { label: "Quiz Agent", tone: "violet" },
  study_planner: { label: "Study Planner", tone: "sky" },
};

const STATUS: Record<AgentRun["status"], { label: string; tone: BadgeTone }> = {
  success: { label: "Thành công", tone: "emerald" },
  clarification: { label: "Hỏi lại", tone: "amber" },
  error: { label: "Lỗi", tone: "rose" },
};

/** Ngăn kéo hiển thị nhật ký thực thi Multi-Agent (Phần 6 của kịch bản demo). */
export function AgentRunsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [runs, setRuns] = useState<AgentRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRuns(await api.listAgentRuns(20));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Chỉ tải khi mở ngăn kéo (không tốn request khi không xem).
  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button className="absolute inset-0 bg-slate-900/20" aria-label="Đóng" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-xl" role="dialog" aria-label="Nhật ký Agent">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="flex items-center gap-2 font-semibold text-slate-900">
              <Activity className="h-4 w-4 text-indigo-600" />
              Nhật ký Agent
            </h2>
            <p className="text-xs text-slate-400">20 lần Supervisor xử lý gần nhất</p>
          </div>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" onClick={load} aria-label="Tải lại" disabled={loading}>
              <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Đóng">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <WorkflowDiagram />

        <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {error && <ErrorState message={error} onRetry={load} />}
          {!error && runs === null && <LoadingState />}
          {runs?.length === 0 && (
            <EmptyState title="Chưa có lần chạy nào" hint="Gửi một tin nhắn trong AI Tutor để Supervisor bắt đầu ghi nhật ký." />
          )}
          {runs?.map((run) => <RunCard key={run.id} run={run} />)}
        </div>
      </aside>
    </div>
  );
}

function WorkflowDiagram() {
  return (
    <div className="border-b border-slate-100 bg-slate-50 px-5 py-3 text-[11px] text-slate-500">
      <p className="mb-1.5 font-medium text-slate-600">Luồng LangGraph</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <code className="rounded bg-white px-1.5 py-0.5">START</code>
        <ArrowRight className="h-3 w-3" />
        <code className="rounded bg-white px-1.5 py-0.5">classify_intent</code>
        <ArrowRight className="h-3 w-3" />
        <span className="flex gap-1">
          <code className="rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-700">rag_tutor</code>|
          <code className="rounded bg-violet-50 px-1.5 py-0.5 text-violet-700">quiz_agent</code>|
          <code className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700">study_planner</code>
        </span>
        <ArrowRight className="h-3 w-3" />
        <code className="rounded bg-white px-1.5 py-0.5">END</code>
      </div>
    </div>
  );
}

function RunCard({ run }: { run: AgentRun }) {
  const agent = run.agent_name ? AGENT[run.agent_name] : undefined;
  const status = STATUS[run.status];
  return (
    <div className="rounded-xl border border-slate-100 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={agent?.tone ?? "slate"}>{agent?.label ?? "Chưa phân loại"}</Badge>
        <Badge tone={status.tone}>{status.label}</Badge>
        <span className="ml-auto text-xs text-slate-400">
          {formatTime(run.created_at)} · {formatDuration(run.duration_ms)}
        </span>
      </div>
      <ol className="mt-2.5 flex flex-wrap items-center gap-1 text-[11px]">
        {run.tools_called.map((tool, i) => (
          <li key={i} className="flex items-center gap-1">
            {i > 0 && <span className="text-slate-300">→</span>}
            <code className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">{tool}</code>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-[11px] text-slate-400">
        Phân loại bằng {run.intent_source === "heuristic" ? "từ khoá (dự phòng)" : "LLM"}
        {run.error_message && <span className="text-rose-500"> · {run.error_message}</span>}
      </p>
    </div>
  );
}
