import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function TableWrap({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("w-full overflow-x-auto rounded-card border border-border bg-surface", className)} {...props} />;
}
export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return <table className={cn("w-full min-w-[640px] border-collapse text-sm", className)} {...props} />;
}
export function Th({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("section-label whitespace-nowrap border-b border-border bg-surface-2/60 px-4 py-2.5 text-left", className)} {...props} />;
}
export function Td({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-b border-border/60 px-4 py-3 align-middle", className)} {...props} />;
}
export function Tr({ className, clickable, ...props }: HTMLAttributes<HTMLTableRowElement> & { clickable?: boolean }) {
  return <tr className={cn("transition-colors odd:bg-transparent even:bg-surface-2/30 hover:bg-surface-2/60", clickable && "cursor-pointer", className)} {...props} />;
}
