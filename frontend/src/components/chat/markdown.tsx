/**
 * Hiển thị phần Markdown đơn giản mà LLM hay trả về: đoạn văn, tiêu đề, danh sách, **đậm**, `code`,
 * khối ```code```. Dựng trực tiếp thành phần tử React (không dùng dangerouslySetInnerHTML) nên nội
 * dung từ LLM/tài liệu không thể chèn HTML hay script vào trang.
 */
import type { ReactNode } from "react";

type Block =
  | { kind: "code"; text: string }
  | { kind: "heading"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "paragraph"; text: string };

function parseBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith("```")) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) code.push(lines[i++]);
      i += 1; // bỏ dòng ``` đóng
      blocks.push({ kind: "code", text: code.join("\n") });
      continue;
    }
    const heading = /^#{1,6}\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", text: heading[1] });
      i += 1;
      continue;
    }
    const bullet = /^\s*[-*•]\s+(.*)$/;
    const numbered = /^\s*\d+[.)]\s+(.*)$/;
    if (bullet.test(line) || numbered.test(line)) {
      const ordered = numbered.test(line);
      const pattern = ordered ? numbered : bullet;
      const items: string[] = [];
      while (i < lines.length && pattern.test(lines[i])) items.push(pattern.exec(lines[i++])![1]);
      blocks.push({ kind: "list", ordered, items });
      continue;
    }
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith("```") &&
      !/^#{1,6}\s/.test(lines[i]) &&
      !bullet.test(lines[i]) &&
      !numbered.test(lines[i])
    ) {
      paragraph.push(lines[i++]);
    }
    blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
  }
  return blocks;
}

/** **đậm** và `code` trong một dòng. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={i} className="rounded bg-slate-100 px-1 py-0.5 text-[0.85em] text-indigo-700">{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-2.5 text-sm leading-relaxed text-slate-700">
      {parseBlocks(text).map((block, i) => {
        switch (block.kind) {
          case "code":
            return (
              <pre key={i} className="overflow-x-auto rounded-xl bg-slate-900 px-4 py-3 text-xs leading-relaxed text-slate-100">
                <code>{block.text}</code>
              </pre>
            );
          case "heading":
            return <p key={i} className="font-semibold text-slate-900">{inline(block.text)}</p>;
          case "list": {
            const List = block.ordered ? "ol" : "ul";
            return (
              <List key={i} className={block.ordered ? "list-decimal space-y-1 pl-5" : "list-disc space-y-1 pl-5"}>
                {block.items.map((item, j) => <li key={j}>{inline(item)}</li>)}
              </List>
            );
          }
          default:
            return (
              <p key={i} className="whitespace-pre-line">
                {inline(block.text)}
              </p>
            );
        }
      })}
    </div>
  );
}
