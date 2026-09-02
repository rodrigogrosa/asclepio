"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { BookOpenText, Clock, Download, Eye, FileText, GitBranch, Search } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { DocFormat, HubCategory, HubDocument, HubDocumentContent } from "@/lib/types";
import { fmtBytes, fmtDate } from "@/lib/utils";
import { useToast } from "@/components/providers/toast-provider";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/modal";
import { MarkdownView } from "@/components/ui/markdown-view";
import { Skeleton, SkeletonCards } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/misc";

const MermaidGraph = dynamic(() => import("@/components/workflows/mermaid-graph").then((m) => m.MermaidGraph), { ssr: false, loading: () => <Skeleton className="h-64" /> });

const FORMAT_TONE: Record<DocFormat, BadgeTone> = { md: "info", pdf: "danger", mmd: "accent" };
const FORMAT_LABEL: Record<DocFormat, string> = { md: "MD", pdf: "PDF", mmd: "MMD" };

/** Baixa o arquivo autenticado (fetch com Bearer → blob → <a download>). */
async function downloadDoc(doc: HubDocument) {
  const { blob, filename } = await api.docsHub.download(doc.id);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || doc.filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function DocsHubView() {
  const toast = useToast();
  const { data, loading, error, reload } = useAsync(() => api.docsHub.list(), []);
  const [q, setQ] = useState("");
  const [reader, setReader] = useState<{ doc: HubDocument; content: HubDocumentContent | null; error: string | null } | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const categories = useMemo<HubCategory[]>(() => {
    const list = data?.categories ?? [];
    const s = q.trim().toLowerCase();
    if (!s) return list;
    return list
      .map((c) => ({ ...c, documents: c.documents.filter((d) => d.title.toLowerCase().includes(s) || d.description.toLowerCase().includes(s)) }))
      .filter((c) => c.documents.length > 0);
  }, [data, q]);
  const shown = categories.reduce((s, c) => s + c.documents.length, 0);

  const openReader = async (doc: HubDocument) => {
    setReader({ doc, content: null, error: null });
    try {
      const content = await api.docsHub.read(doc.id);
      setReader((r) => (r && r.doc.id === doc.id ? { ...r, content } : r));
    } catch (e) {
      setReader((r) => (r && r.doc.id === doc.id ? { ...r, error: errorMessage(e, "Não foi possível carregar o documento") } : r));
    }
  };

  const download = async (doc: HubDocument) => {
    setDownloading(doc.id);
    try {
      await downloadDoc(doc);
      toast.success("Download iniciado", doc.filename);
    } catch (e) {
      toast.error("Não foi possível baixar", errorMessage(e));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documentação"
        description="Central de evidências do projeto: relatórios, decisões de arquitetura, dados & ML, segurança e operação — os documentos que sustentam a plataforma."
      />

      <div className="flex flex-wrap items-center gap-3">
        <Input placeholder="Buscar por título ou descrição…" value={q} onChange={(e) => setQ(e.target.value)} leftIcon={<Search className="h-4 w-4" />} wrapperClassName="w-full sm:w-80" aria-label="Buscar documentos" />
        <span className="text-xs text-muted">
          {q ? `${shown} de ${data?.total ?? 0} documento(s)` : `${data?.total ?? 0} documento(s)`}
        </span>
      </div>

      {loading && !data ? (
        <SkeletonCards n={6} />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={() => void reload()} />
      ) : categories.length === 0 ? (
        <EmptyState icon={<BookOpenText className="h-5 w-5" />} title="Nenhum documento encontrado" description={q ? "Tente outros termos de busca." : "A biblioteca está vazia."} />
      ) : (
        categories.map((cat) => (
          <section key={cat.id} aria-label={cat.title}>
            <h2 className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wider text-text">
              <BookOpenText className="h-4 w-4 text-primary" /> {cat.title}
            </h2>
            <p className="mb-3 mt-0.5 text-xs text-muted">{cat.description}</p>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {cat.documents.map((d) => (
                <article key={d.id} className="flex flex-col rounded-card border border-border bg-surface p-4 transition-colors hover:border-primary/50">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold leading-snug text-text">{d.title}</p>
                    <Badge tone={FORMAT_TONE[d.format]} size="sm" icon={d.format === "mmd" ? <GitBranch className="h-2.5 w-2.5" /> : <FileText className="h-2.5 w-2.5" />}>
                      {FORMAT_LABEL[d.format]}
                    </Badge>
                  </div>
                  <p className="mt-1 flex-1 text-xs leading-relaxed text-muted">{d.description}</p>
                  <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
                    <span>{fmtBytes(d.size_bytes)}</span>
                    {d.updated_at && (
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3 w-3" /> atualizado em {fmtDate(d.updated_at)}
                      </span>
                    )}
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    {d.readable && (
                      <Button size="sm" variant="secondary" onClick={() => void openReader(d)}>
                        <Eye className="h-3.5 w-3.5" /> Ler
                      </Button>
                    )}
                    {d.downloadable && (
                      <Button size="sm" variant="outline" onClick={() => void download(d)} loading={downloading === d.id}>
                        <Download className="h-3.5 w-3.5" /> Baixar
                      </Button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))
      )}

      <Drawer
        open={!!reader}
        onClose={() => setReader(null)}
        title={reader?.doc.title ?? ""}
        description={reader ? `${reader.doc.filename} · ${fmtBytes(reader.doc.size_bytes)}${reader.doc.updated_at ? ` · atualizado em ${fmtDate(reader.doc.updated_at)}` : ""}` : undefined}
        width="max-w-4xl"
        footer={
          reader?.doc.downloadable ? (
            <Button variant="outline" size="sm" onClick={() => reader && void download(reader.doc)} loading={downloading === reader?.doc.id}>
              <Download className="h-3.5 w-3.5" /> Baixar original
            </Button>
          ) : undefined
        }
      >
        {reader &&
          (reader.error ? (
            <ErrorState message={reader.error} onRetry={() => void openReader(reader.doc)} />
          ) : !reader.content ? (
            <div className="space-y-2">
              {[0, 1, 2, 3, 4, 5, 6].map((i) => (
                <Skeleton key={i} className={i % 3 === 0 ? "h-4 w-2/3" : "h-4"} />
              ))}
            </div>
          ) : reader.content.format === "mmd" ? (
            <MermaidGraph code={reader.content.content} title={reader.doc.id} className="min-h-[320px]" />
          ) : (
            /* tabelas largas rolam horizontalmente dentro do drawer */
            <div className="[&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto">
              <MarkdownView content={reader.content.content} />
            </div>
          ))}
      </Drawer>
    </div>
  );
}
