"use client";

import { useMemo, useState, type FormEvent } from "react";
import { BookOpen, Clock, Database, FileText, Hash, Layers, RefreshCw, Search, Tag } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { DocType, KnowledgeDocument, KnowledgeDocumentDetail, KnowledgeSearchResponse } from "@/lib/types";
import { cn, fmtDate, fmtNumber } from "@/lib/utils";
import { useAuth } from "@/components/providers/auth-provider";
import { useToast } from "@/components/providers/toast-provider";
import { Card, CardBody } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { DocTypeBadge, DOC_TYPE_LABEL } from "@/components/ui/status-badges";
import { Drawer } from "@/components/ui/modal";
import { MarkdownView } from "@/components/ui/markdown-view";
import { Skeleton, SkeletonCards } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/misc";
import { CitationCard } from "@/components/chat/sources-panel";

const TYPES: DocType[] = ["protocolo", "faq", "modelo", "prontuario"];

export function KnowledgeView() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const [type, setType] = useState<DocType | "">("");
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<KnowledgeSearchResponse | null>(null);
  const [doc, setDoc] = useState<KnowledgeDocumentDetail | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const { data, loading, error, reload } = useAsync(() => api.knowledge.documents(type), [type]);

  const grouped = useMemo(() => {
    const g: Record<DocType, KnowledgeDocument[]> = { protocolo: [], faq: [], modelo: [], prontuario: [] };
    (data ?? []).forEach((d) => g[d.doc_type].push(d));
    return g;
  }, [data]);
  const totals = useMemo(() => ({ docs: data?.length ?? 0, chunks: (data ?? []).reduce((s, d) => s + d.chunks, 0), chars: (data ?? []).reduce((s, d) => s + d.size_chars, 0) }), [data]);

  const search = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) {
      setResults(null);
      return;
    }
    setSearching(true);
    try {
      setResults(await api.knowledge.search(query.trim(), 5, type));
    } catch (err) {
      toast.error("Falha na busca", errorMessage(err));
    } finally {
      setSearching(false);
    }
  };

  const openDoc = async (id: string) => {
    setDocLoading(true);
    setDoc(null);
    try {
      setDoc(await api.knowledge.document(id));
    } catch (err) {
      toast.error("Falha ao abrir documento", errorMessage(err));
    } finally {
      setDocLoading(false);
    }
  };

  const reindex = async () => {
    if (!confirm("Reindexar toda a base de conhecimento? Isso pode levar alguns minutos.")) return;
    setReindexing(true);
    try {
      const r = await api.knowledge.reindex();
      toast.success("Reindexação concluída", `${r.documents} documentos · ${r.chunks} chunks · ${(r.duration_ms / 1000).toFixed(1)} s`);
      reload();
    } catch (err) {
      toast.error("Falha ao reindexar", errorMessage(err));
    } finally {
      setReindexing(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Base de conhecimento"
        description="Protocolos, FAQs, modelos de documento e prontuários sintéticos indexados para o RAG."
        actions={
          hasRole("admin") && (
            <Button variant="outline" onClick={reindex} loading={reindexing}>
              <RefreshCw className="h-4 w-4" /> Reindexar
            </Button>
          )
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { l: "Documentos", v: totals.docs, i: FileText },
          { l: "Chunks indexados", v: totals.chunks, i: Layers },
          { l: "Caracteres", v: fmtNumber(totals.chars), i: Hash },
        ].map((k) => (
          <Card key={k.l} className="flex items-center gap-3 px-4 py-3">
            <k.i className="h-5 w-5 text-primary" />
            <div>
              <p className="section-label">{k.l}</p>
              <p className="font-display text-xl font-extrabold">{loading && !data ? "…" : k.v}</p>
            </div>
          </Card>
        ))}
      </div>

      {/* Busca semântica */}
      <Card>
        <CardBody>
          <form onSubmit={search} className="flex flex-col gap-2 sm:flex-row">
            <Input placeholder="Busca semântica: ex. “prazo para coleta de hemocultura na sepse”" value={query} onChange={(e) => setQuery(e.target.value)} leftIcon={<Search className="h-4 w-4" />} wrapperClassName="flex-1" aria-label="Busca semântica" />
            <Select value={type} onChange={(e) => setType(e.target.value as DocType | "")} wrapperClassName="sm:w-44" aria-label="Tipo de documento">
              <option value="">Todos os tipos</option>
              {TYPES.map((t) => <option key={t} value={t}>{DOC_TYPE_LABEL[t]}</option>)}
            </Select>
            <Button type="submit" loading={searching}><Search className="h-4 w-4" /> Buscar</Button>
          </form>
          {results && (
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between">
                <p className="section-label">Resultados ({results.results.length})</p>
                <p className="inline-flex items-center gap-1 text-[11px] text-muted"><Clock className="h-3 w-3" /> {results.latency_ms} ms · embeddings + similaridade</p>
              </div>
              {results.results.length ? (
                <ol className="grid gap-2 lg:grid-cols-2">
                  {results.results.map((c) => (
                    <button key={`${c.id}-${c.source_id}`} onClick={() => openDoc(c.source_id)} className="text-left">
                      <CitationCard c={c} />
                    </button>
                  ))}
                </ol>
              ) : (
                <EmptyState title="Nada encontrado" description="Tente outros termos." />
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {error && !data ? (
        <ErrorState message={error} onRetry={() => reload()} />
      ) : loading && !data ? (
        <SkeletonCards n={6} />
      ) : (
        (type ? [type] : TYPES).map((t) =>
          grouped[t].length ? (
            <section key={t}>
              <h2 className="mb-3 flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wider text-text">
                <BookOpen className="h-4 w-4 text-primary" /> {DOC_TYPE_LABEL[t]}s <span className="text-muted">({grouped[t].length})</span>
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {grouped[t].map((d) => (
                  <button key={d.id} onClick={() => openDoc(d.id)} className="group rounded-card border border-border bg-surface p-4 text-left transition-colors hover:border-primary/60">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold leading-snug text-text group-hover:text-primary-hover">{d.title}</p>
                      <DocTypeBadge type={d.doc_type} />
                    </div>
                    <p className="mt-1 truncate font-mono text-[10px] text-muted">{d.path}</p>
                    <div className="mt-3 flex flex-wrap gap-1">
                      {d.tags.map((tg) => <Badge key={tg} tone="neutral" size="sm" icon={<Tag className="h-2.5 w-2.5" />}>{tg}</Badge>)}
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
                      <span className="inline-flex items-center gap-1"><Layers className="h-3 w-3" /> {d.chunks} chunks</span>
                      {d.version && <span>v{d.version}</span>}
                      {d.category && <span>{d.category}</span>}
                      {d.updated_at && <span className="ml-auto">{fmtDate(d.updated_at)}</span>}
                    </div>
                  </button>
                ))}
              </div>
            </section>
          ) : null,
        )
      )}
      {data && !data.length && <EmptyState icon={<Database className="h-5 w-5" />} title="Nenhum documento" description="A base está vazia para este filtro." />}

      <Drawer open={docLoading || !!doc} onClose={() => { setDoc(null); setDocLoading(false); }} title={doc?.title ?? "Carregando…"} description={doc ? `${doc.path}${doc.version ? ` · v${doc.version}` : ""} · ${doc.chunks} chunks` : undefined}>
        {docLoading || !doc ? (
          <div className="space-y-2">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className={cn("h-4", i % 3 === 0 && "w-2/3")} />)}</div>
        ) : (
          <>
            <div className="mb-4 flex flex-wrap gap-1.5">
              <DocTypeBadge type={doc.doc_type} size="md" />
              {doc.category && <Badge tone="neutral">{doc.category}</Badge>}
              {doc.tags.map((t) => <Badge key={t} tone="primary" size="sm">{t}</Badge>)}
            </div>
            <MarkdownView content={doc.content} />
          </>
        )}
      </Drawer>
    </div>
  );
}
