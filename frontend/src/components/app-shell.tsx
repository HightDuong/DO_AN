"use client";

import { Activity, BookOpen, CalendarCheck, GraduationCap, LayoutDashboard, MessageCircle, Trophy } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { AgentRunsDrawer } from "@/components/agent-runs-drawer";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Knowledge Library", icon: BookOpen },
  { href: "/chat", label: "AI Tutor", icon: MessageCircle },
  { href: "/quizzes", label: "Quiz Center", icon: Trophy },
  { href: "/study-plans", label: "Study Planner", icon: CalendarCheck },
] as const;

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

type BackendStatus = "checking" | "online" | "offline";

function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>("checking");
  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .health()
        .then(() => alive && setStatus("online"))
        .catch(() => alive && setStatus("offline"));
    void check();
    const timer = setInterval(check, 30_000); // nhẹ: 30 giây mới kiểm tra lại một lần
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  return status;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [runsOpen, setRunsOpen] = useState(false);
  const backend = useBackendStatus();

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Sidebar (màn hình rộng) */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-slate-100 bg-white px-4 py-6 md:flex">
        <Link href="/" className="mb-8 flex items-center gap-2.5 px-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white">
            <GraduationCap className="h-5 w-5" />
          </span>
          <span>
            <span className="block text-base font-bold text-slate-900">StudyMate AI</span>
            <span className="block text-xs text-slate-400">Cơ sở dữ liệu</span>
          </span>
        </Link>

        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                isActive(pathname, href)
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-800",
              )}
            >
              <Icon className="h-[18px] w-[18px]" />
              {label}
            </Link>
          ))}
        </nav>

        <div className="space-y-3 border-t border-slate-100 pt-4">
          <button
            onClick={() => setRunsOpen(true)}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-slate-500 hover:bg-slate-50 hover:text-slate-800"
          >
            <Activity className="h-[18px] w-[18px]" />
            Nhật ký Agent
          </button>
          <BackendIndicator status={backend} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Thanh điều hướng (màn hình hẹp) */}
        <header className="sticky top-0 z-10 flex items-center gap-1 overflow-x-auto border-b border-slate-100 bg-white px-3 py-2 md:hidden">
          {NAV.map(({ href, icon: Icon, label }) => (
            <Link
              key={href}
              href={href}
              aria-label={label}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium",
                isActive(pathname, href) ? "bg-indigo-50 text-indigo-700" : "text-slate-500",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
          <button onClick={() => setRunsOpen(true)} aria-label="Nhật ký Agent" className="ml-auto shrink-0 p-2 text-slate-500">
            <Activity className="h-4 w-4" />
          </button>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>

      <AgentRunsDrawer open={runsOpen} onClose={() => setRunsOpen(false)} />
    </div>
  );
}

function BackendIndicator({ status }: { status: BackendStatus }) {
  const style = {
    checking: { dot: "bg-slate-300", text: "Đang kiểm tra backend…" },
    online: { dot: "bg-emerald-500", text: "Backend đang chạy" },
    offline: { dot: "bg-rose-500", text: "Không kết nối được backend" },
  }[status];
  return (
    <p className="flex items-center gap-2 px-3 text-xs text-slate-400">
      <span className={cn("h-2 w-2 rounded-full", style.dot)} />
      {style.text}
    </p>
  );
}
