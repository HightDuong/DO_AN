/**
 * Component giao diện cơ bản theo phong cách shadcn/ui, viết bằng Tailwind thuần
 * (không dùng Radix để giữ bundle và node_modules nhẹ).
 */
import { AlertTriangle, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-2xl border border-slate-100 bg-white shadow-sm", className)} {...props} />;
}

export function CardHeader({ title, icon, action }: { title: string; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-5 pt-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
        {icon}
        {title}
      </h2>
      {action}
    </div>
  );
}

const BADGE_TONES = {
  slate: "bg-slate-100 text-slate-600",
  indigo: "bg-indigo-50 text-indigo-700",
  emerald: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  rose: "bg-rose-50 text-rose-700",
  sky: "bg-sky-50 text-sky-700",
  violet: "bg-violet-50 text-violet-700",
} as const;

export type BadgeTone = keyof typeof BADGE_TONES;

export function Badge({
  tone = "slate",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium",
        BADGE_TONES[tone],
        className,
      )}
      {...props}
    />
  );
}

const BUTTON_VARIANTS = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300",
  secondary: "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400",
  ghost: "text-slate-600 hover:bg-slate-100 disabled:text-slate-300",
  danger: "text-rose-600 hover:bg-rose-50 disabled:text-rose-300",
} as const;

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof BUTTON_VARIANTS;
  size?: "sm" | "md" | "icon";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-colors disabled:cursor-not-allowed",
        size === "sm" && "px-3 py-1.5 text-sm",
        size === "md" && "px-4 py-2 text-sm",
        size === "icon" && "h-8 w-8",
        BUTTON_VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}

/** Thanh tiến độ kiểu "thanh kinh nghiệm". `value` trong khoảng 0..1. */
export function ProgressBar({ value, barClassName, className }: { value: number; barClassName?: string; className?: string }) {
  const width = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div
      className={cn("h-2.5 w-full overflow-hidden rounded-full bg-slate-100", className)}
      role="progressbar"
      aria-valuenow={Math.round(width)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={cn("h-full rounded-full transition-[width] duration-500", barClassName ?? "bg-indigo-500")} style={{ width: `${width}%` }} />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin", className)} aria-hidden />;
}

export function LoadingState({ label = "Đang tải…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-400">
      <Spinner />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl bg-rose-50 px-4 py-6 text-center text-sm text-rose-700">
      <span className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4" />
        {message}
      </span>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Thử lại
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      {icon && <div className="text-slate-300">{icon}</div>}
      <p className="text-sm font-medium text-slate-500">{title}</p>
      {hint && <p className="max-w-sm text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {action}
    </div>
  );
}
