import Link from "next/link";
import { LogoMark } from "@/components/brand/logo";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-bg px-4 text-center">
      <LogoMark size={72} />
      <p className="font-display text-6xl font-extrabold brand-gradient-text">404</p>
      <h1 className="font-display text-lg font-bold uppercase tracking-wide text-text">Página não encontrada</h1>
      <p className="max-w-sm text-sm text-muted">O recurso que você procura não existe ou foi movido.</p>
      <Link href="/" className="mt-2 rounded-control bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-hover">
        Voltar ao dashboard
      </Link>
    </div>
  );
}
