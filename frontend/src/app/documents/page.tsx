"use client";

import { CheckCircle2, FileText, Trash2, UploadCloud, XCircle } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, Spinner } from "@/components/ui";
import { api, type DocumentOut, type DocumentStatus } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import { errorMessage, useApi } from "@/lib/use-api";

const MAX_UPLOAD_MB = 20; // khớp giới hạn MAX_UPLOAD_MB của backend

type Upload = { key: string; name: string; state: "processing" | "done" | "failed"; message?: string };

export default function DocumentsPage() {
  const docs = useApi(api.listDocuments);
  const [uploads, setUploads] = useState<Upload[]>([]);

  const updateUpload = (key: string, patch: Partial<Upload>) =>
    setUploads((list) => list.map((u) => (u.key === key ? { ...u, ...patch } : u)));

  // Nạp lần lượt từng file: mỗi file backend phải trích xuất + gọi embedding, chạy song song dễ chạm quota.
  async function uploadFiles(files: File[]) {
    const queued = files.map((file) => ({ file, key: `${file.name}-${file.size}-${Date.now()}` }));
    setUploads((list) => [
      ...queued.map(({ file, key }) => ({ key, name: file.name, state: "processing" as const })),
      ...list,
    ]);
    for (const { file, key } of queued) {
      const problem = validateFile(file);
      if (problem) {
        updateUpload(key, { state: "failed", message: problem });
        continue;
      }
      try {
        const result = await api.uploadDocument(file);
        updateUpload(key, { state: "done", message: `${result.page_count ?? "?"} trang · ${result.chunk_count} đoạn đã lập chỉ mục` });
      } catch (e) {
        updateUpload(key, { state: "failed", message: errorMessage(e) });
      }
      void docs.reload();
    }
  }

  async function remove(doc: DocumentOut) {
    if (!window.confirm(`Xoá "${doc.title}"? Các đoạn đã lập chỉ mục và nguồn trích dẫn liên quan cũng bị xoá.`)) return;
    try {
      await api.deleteDocument(doc.id);
      docs.setData((list) => list?.filter((d) => d.id !== doc.id) ?? null);
    } catch (e) {
      window.alert(errorMessage(e));
    }
  }

  return (
    <>
      <PageHeader title="Knowledge Library" description="Giáo trình và tài liệu làm nguồn cho AI Tutor, Quiz và Study Planner" />
      <div className="space-y-6">
        <Dropzone onFiles={uploadFiles} busy={uploads.some((u) => u.state === "processing")} />
        {uploads.length > 0 && <UploadList uploads={uploads} onClear={() => setUploads((l) => l.filter((u) => u.state === "processing"))} />}

        <Card>
          <div className="flex items-center justify-between px-5 pt-5">
            <h2 className="text-sm font-semibold text-slate-700">Tài liệu của bạn</h2>
            {docs.data && <span className="text-xs text-slate-400">{docs.data.length} tài liệu</span>}
          </div>
          <div className="p-5 pt-3">
            {docs.error && <ErrorState message={docs.error} onRetry={docs.reload} />}
            {!docs.error && docs.loading && !docs.data && <LoadingState />}
            {docs.data?.length === 0 && (
              <EmptyState icon={<FileText className="h-8 w-8" />} title="Chưa có tài liệu nào" hint="Kéo-thả file PDF giáo trình vào khung phía trên." />
            )}
            {docs.data && docs.data.length > 0 && (
              <ul className="divide-y divide-slate-50">
                {docs.data.map((doc) => (
                  <DocumentRow key={doc.id} doc={doc} onDelete={() => remove(doc)} />
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>
    </>
  );
}

function validateFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") return "Chỉ hỗ trợ file PDF.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `File vượt quá ${MAX_UPLOAD_MB} MB.`;
  return null;
}

function Dropzone({ onFiles, busy }: { onFiles: (files: File[]) => void; busy: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) onFiles(files);
  }

  return (
    <button
      type="button"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
        dragging ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white hover:border-indigo-300 hover:bg-slate-50",
      )}
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
        {busy ? <Spinner className="h-6 w-6" /> : <UploadCloud className="h-6 w-6" />}
      </span>
      <span className="text-sm font-medium text-slate-700">Kéo-thả file PDF vào đây hoặc bấm để chọn</span>
      <span className="text-xs text-slate-400">
        PDF có lớp chữ (không phải bản scan), tối đa {MAX_UPLOAD_MB} MB. Mỗi file mất khoảng vài chục giây để lập chỉ mục.
      </span>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) onFiles(files);
        }}
      />
    </button>
  );
}

function UploadList({ uploads, onClear }: { uploads: Upload[]; onClear: () => void }) {
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Đang tải lên</h2>
        <Button variant="ghost" size="sm" onClick={onClear}>
          Ẩn mục đã xong
        </Button>
      </div>
      <ul className="space-y-2">
        {uploads.map((u) => (
          <li key={u.key} className="flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-2.5 text-sm">
            {u.state === "processing" && <Spinner className="text-indigo-500" />}
            {u.state === "done" && <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
            {u.state === "failed" && <XCircle className="h-4 w-4 text-rose-500" />}
            <span className="min-w-0 flex-1 truncate font-medium text-slate-700">{u.name}</span>
            <span className={cn("text-xs", u.state === "failed" ? "text-rose-600" : "text-slate-400")}>
              {u.state === "processing" ? "Đang trích xuất & lập chỉ mục…" : u.message}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const STATUS_BADGE: Record<DocumentStatus, { label: string; tone: "emerald" | "indigo" | "rose" | "slate"; spinning?: boolean }> = {
  indexed: { label: "Sẵn sàng", tone: "emerald" },
  processing: { label: "Đang xử lý", tone: "indigo", spinning: true },
  uploaded: { label: "Đã tải lên", tone: "slate", spinning: true },
  failed: { label: "Lỗi", tone: "rose" },
};

function DocumentRow({ doc, onDelete }: { doc: DocumentOut; onDelete: () => void }) {
  const badge = STATUS_BADGE[doc.status];
  return (
    <li className="flex items-center gap-4 py-3.5">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-50 text-slate-400">
        <FileText className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-800">{doc.title}</p>
        <p className="text-xs text-slate-400">
          {doc.page_count !== null ? `${doc.page_count} trang` : "? trang"} · {doc.chunk_count} đoạn · nạp {formatDate(doc.created_at)}
          {doc.license && ` · ${doc.license}`}
        </p>
      </div>
      <Badge tone={badge.tone}>
        {badge.spinning && <Spinner className="h-3 w-3" />}
        {badge.label}
      </Badge>
      <Button variant="danger" size="icon" onClick={onDelete} aria-label={`Xoá ${doc.title}`} title="Xoá tài liệu">
        <Trash2 className="h-4 w-4" />
      </Button>
    </li>
  );
}
