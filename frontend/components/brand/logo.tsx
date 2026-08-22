import Image from "next/image";
import { cn } from "@/lib/utils";

export function LogoMark({ size = 36, className }: { size?: number; className?: string }) {
  return <Image src="/brand/asclepio-mark.svg" alt="Asclépio" width={size} height={size} priority className={cn("shrink-0 rounded-[22%]", className)} />;
}

export function Wordmark({ className, size = "md" }: { className?: string; size?: "sm" | "md" | "lg" }) {
  const s = { sm: "text-base", md: "text-xl", lg: "text-4xl" }[size];
  return (
    <span className={cn("font-display font-extrabold uppercase leading-none tracking-[0.04em] text-white", s, className)}>
      ASCL<span className="text-primary">É</span>PIO
    </span>
  );
}

export function Logo({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <LogoMark size={compact ? 32 : 40} />
      {!compact && (
        <div className="flex flex-col">
          <Wordmark />
          <span className="text-[7px] font-semibold uppercase leading-[1.3] tracking-[0.16em] text-primary">Assistente Clínico<br />Inteligente</span>
        </div>
      )}
    </div>
  );
}
