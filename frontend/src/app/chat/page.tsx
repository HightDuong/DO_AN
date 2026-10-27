"use client";

import { Bot, Filter, MessageCirclePlus, MessagesSquare, SendHorizontal, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { AssistantMessage } from "@/components/chat/assistant-message";
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, Spinner } from "@/components/ui";
import { api, type ChatResponse, type ChatSession, type DocumentOut } from "@/lib/api";
import { cn } from "@/lib/cn";
import { timeAgo } from "@/lib/format";
import { errorMessage, useApi } from "@/lib/use-api";

type DisplayMessage = { id: string; role: "user" | "assistant"; content: string; payload: ChatResponse | null };

const SUGGESTIONS = [
  "So sánh khóa chính và khóa ngoại. Vì sao KetQua.MaSV không được NULL?",
  "Tạo 5 câu trắc nghiệm SQL về WHERE/HAVING và LEFT JOIN",
  "Tôi nên học gì trong ba ngày tới?",
  "B+ tree hoạt động như thế nào?",
];

export default function ChatPage() {
  const sessions = useApi(api.listChatSessions);
  const documents = useApi(api.listDocuments);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [docFilter, setDocFilter] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  async function openSession(session: ChatSession) {
    if (sending) return;
    setSessionId(session.id);
    setHistoryError(null);
    setLoadingMessages(true);
    try {
      const history = await api.listChatMessages(session.id);
      setMessages(history.map((m) => ({ id: m.id, role: m.role, content: m.content, payload: m.payload })));
    } catch (e) {
      setHistoryError(errorMessage(e));
      setMessages([]);
    } finally {
      setLoadingMessages(false);
    }
  }

  function newConversation() {
    if (sending) return;
    setSessionId(null);
    setMessages([]);
    setHistoryError(null);
  }

  async function send(question: string) {
    const text = question.trim();
    if (!text || sending) return;
    setMessages((list) => [...list, { id: `local-${Date.now()}`, role: "user", content: text, payload: null }]);
    setSending(true);
    try {
      const response = await api.sendChat({
        question: text,
        session_id: sessionId,
        document_ids: docFilter.length ? docFilter : null,
      });
      if (response.session_id) setSessionId(response.session_id);
      setMessages((list) => [
        ...list,
        { id: response.message_id ?? `reply-${Date.now()}`, role: "assistant", content: response.message, payload: response },
      ]);
      void sessions.reload();
    } catch (e) {
      const failure: ChatResponse = { type: "error", intent: null, message: errorMessage(e) };
      setMessages((list) => [...list, { id: `error-${Date.now()}`, role: "assistant", content: failure.message, payload: failure }]);
    } finally {
      setSending(false);
    }
  }

  const indexedDocs = (documents.data ?? []).filter((d) => d.status === "indexed");

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-5 md:h-[calc(100vh-4rem)]">
      {/* Danh sách phiên */}
      <Card className="hidden w-64 shrink-0 flex-col lg:flex">
        <div className="p-3">
          <Button className="w-full" onClick={newConversation} disabled={sending}>
            <MessageCirclePlus className="h-4 w-4" />
            Cuộc trò chuyện mới
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {sessions.error && <p className="px-2 text-xs text-rose-600">{sessions.error}</p>}
          {sessions.loading && !sessions.data && <LoadingState label="" />}
          {sessions.data?.length === 0 && <p className="px-3 py-4 text-center text-xs text-slate-400">Chưa có cuộc trò chuyện nào</p>}
          <ul className="space-y-0.5">
            {sessions.data?.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => openSession(s)}
                  className={cn(
                    "w-full rounded-xl px-3 py-2.5 text-left transition-colors",
                    s.id === sessionId ? "bg-indigo-50" : "hover:bg-slate-50",
                  )}
                >
                  <p className={cn("truncate text-sm", s.id === sessionId ? "font-medium text-indigo-700" : "text-slate-700")}>
                    {s.title}
                  </p>
                  <p className="text-xs text-slate-400">
                    {timeAgo(s.updated_at)} · {s.message_count} tin
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Card>

      {/* Khung hội thoại */}
      <Card className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-3">
          <Bot className="h-5 w-5 text-indigo-600" />
          <h1 className="text-sm font-semibold text-slate-800">AI Tutor</h1>
          <span className="text-xs text-slate-400">hỏi đáp có trích dẫn · tạo quiz · lập kế hoạch</span>
          <Button variant="ghost" size="sm" className="ml-auto lg:hidden" onClick={newConversation} disabled={sending}>
            <MessageCirclePlus className="h-4 w-4" />
            Mới
          </Button>
        </div>

        {indexedDocs.length > 1 && <DocumentFilter docs={indexedDocs} selected={docFilter} onChange={setDocFilter} />}

        <div className="flex-1 overflow-y-auto px-4 py-5 md:px-6">
          {historyError && <ErrorState message={historyError} />}
          {loadingMessages && <LoadingState label="Đang tải lịch sử…" />}
          {!loadingMessages && !historyError && messages.length === 0 && <Welcome onPick={send} disabled={sending} />}
          <div className="space-y-5">
            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="flex justify-end">
                  <p className="max-w-[80%] whitespace-pre-line rounded-2xl rounded-tr-md bg-indigo-600 px-4 py-2.5 text-sm text-white">
                    {m.content}
                  </p>
                </div>
              ) : (
                <div key={m.id} className="flex gap-3">
                  <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                    <Sparkles className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 max-w-[85%] flex-1">
                    {m.payload ? <AssistantMessage response={m.payload} /> : <p className="text-sm text-slate-700">{m.content}</p>}
                  </div>
                </div>
              ),
            )}
            {sending && (
              <div className="flex items-center gap-3 text-sm text-slate-400">
                <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                  <Spinner />
                </span>
                Đang tìm trong giáo trình và soạn câu trả lời…
              </div>
            )}
          </div>
          <div ref={bottomRef} />
        </div>

        <Composer onSend={send} disabled={sending} />
      </Card>
    </div>
  );
}

function Welcome({ onPick, disabled }: { onPick: (q: string) => void; disabled: boolean }) {
  return (
    <div className="mx-auto max-w-xl py-6">
      <EmptyState
        icon={<MessagesSquare className="h-10 w-10" />}
        title="Bạn muốn ôn gì hôm nay?"
        hint="Hỏi kiến thức trong giáo trình (có trích dẫn trang), yêu cầu tạo bài trắc nghiệm, hoặc nhờ lập kế hoạch ôn tập."
      />
      <div className="grid gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            disabled={disabled}
            onClick={() => onPick(s)}
            className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-left text-sm text-slate-600 transition-colors hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function DocumentFilter({ docs, selected, onChange }: { docs: DocumentOut[]; selected: string[]; onChange: (ids: string[]) => void }) {
  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-100 px-5 py-2">
      <Filter className="h-3.5 w-3.5 text-slate-400" />
      <span className="mr-1 text-xs text-slate-400">Tìm trong:</span>
      <button onClick={() => onChange([])}>
        <Badge tone={selected.length === 0 ? "indigo" : "slate"}>Tất cả tài liệu</Badge>
      </button>
      {docs.map((d) => (
        <button key={d.id} onClick={() => toggle(d.id)} title={d.title}>
          <Badge tone={selected.includes(d.id) ? "indigo" : "slate"} className="max-w-48 truncate">
            {d.title}
          </Badge>
        </button>
      ))}
    </div>
  );
}

function Composer({ onSend, disabled }: { onSend: (text: string) => void; disabled: boolean }) {
  const [text, setText] = useState("");

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!text.trim() || disabled) return;
    onSend(text);
    setText("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="flex items-end gap-2 border-t border-slate-100 p-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        maxLength={1000}
        placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
        className="max-h-40 min-h-11 flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm outline-none focus:border-indigo-300 focus:bg-white focus:ring-2 focus:ring-indigo-100"
      />
      <Button type="submit" disabled={disabled || !text.trim()} className="h-11" aria-label="Gửi">
        {disabled ? <Spinner /> : <SendHorizontal className="h-4 w-4" />}
      </Button>
    </form>
  );
}
