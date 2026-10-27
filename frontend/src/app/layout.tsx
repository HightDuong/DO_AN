import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { AppShell } from "@/components/app-shell";

import "./globals.css";

const inter = Inter({ subsets: ["latin", "vietnamese"], display: "swap" });

export const metadata: Metadata = {
  title: "StudyMate AI",
  description: "Trợ lý học tập Cơ sở dữ liệu: hỏi đáp có trích dẫn, quiz và kế hoạch ôn tập cá nhân hoá",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi" className={inter.className}>
      <body className="bg-slate-50 text-slate-800 antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
