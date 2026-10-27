/** Ghép className, bỏ giá trị rỗng/false (thay cho clsx để không thêm thư viện). */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
