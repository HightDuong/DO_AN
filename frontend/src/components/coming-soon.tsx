import { Construction } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Card, PageHeader } from "@/components/ui";

/** Trang tạm cho các màn hình sẽ làm ở bước sau (để link trong sidebar / thẻ hành động không lỗi). */
export function ComingSoon({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-500">
          <Construction className="h-6 w-6" />
        </span>
        <p className="font-medium text-slate-700">Màn hình này đang được xây dựng</p>
        <p className="max-w-md text-sm text-slate-400">
          {children ?? "Backend đã sẵn sàng; giao diện sẽ có ở bước tiếp theo."}
        </p>
        <Link href="/chat" className="text-sm font-medium text-indigo-600 hover:underline">
          Quay lại AI Tutor
        </Link>
      </Card>
    </>
  );
}
