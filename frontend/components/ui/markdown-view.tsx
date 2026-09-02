"use client";

import dynamic from "next/dynamic";
import { useMemo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

// Diagramas ```mermaid dentro do markdown são renderizados com o mesmo componente do grafo
// (com zoom e exportação PNG/PDF), em vez de aparecerem como texto de código.
const MermaidGraph = dynamic(() => import("@/components/workflows/mermaid-graph").then((m) => m.MermaidGraph), {
  ssr: false,
  loading: () => <Skeleton className="h-48" />,
});

function extractText(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (node && typeof node === "object" && "props" in node) {
    return extractText((node as { props: { children?: ReactNode } }).props.children);
  }
  return "";
}

type Props = {
  content: string;
  className?: string;
  /** Quando informado, `[n]` vira chip clicável */
  onCitationClick?: (n: number) => void;
  citationCount?: number;
};

const CITE_RE = /\[(\d{1,2})\]/g;

function renderWithCitations(children: ReactNode, onClick?: (n: number) => void, max?: number): ReactNode {
  if (!onClick) return children;
  const walk = (node: ReactNode, keyPrefix = "c"): ReactNode => {
    if (typeof node === "string") {
      if (!CITE_RE.test(node)) return node;
      CITE_RE.lastIndex = 0;
      const out: ReactNode[] = [];
      let last = 0;
      let m: RegExpExecArray | null;
      let i = 0;
      while ((m = CITE_RE.exec(node)) !== null) {
        const n = Number(m[1]);
        if (max != null && n > max) continue;
        out.push(node.slice(last, m.index));
        out.push(
          <button key={`${keyPrefix}-${i++}`} type="button" className="cite" onClick={() => onClick(n)} aria-label={`Ver fonte ${n}`} title={`Fonte [${n}]`}>
            {n}
          </button>,
        );
        last = m.index + m[0].length;
      }
      out.push(node.slice(last));
      return out;
    }
    if (Array.isArray(node)) return node.map((c, i) => walk(c, `${keyPrefix}${i}`));
    return node;
  };
  return walk(children);
}

export function MarkdownView({ content, className, onCitationClick, citationCount }: Props) {
  const components = useMemo(
    () => ({
      p: ({ children }: { children?: ReactNode }) => <p>{renderWithCitations(children, onCitationClick, citationCount)}</p>,
      li: ({ children }: { children?: ReactNode }) => <li>{renderWithCitations(children, onCitationClick, citationCount)}</li>,
      td: ({ children }: { children?: ReactNode }) => <td>{renderWithCitations(children, onCitationClick, citationCount)}</td>,
      strong: ({ children }: { children?: ReactNode }) => <strong>{renderWithCitations(children, onCitationClick, citationCount)}</strong>,
      pre: ({ children }: { children?: ReactNode }) => {
        const child = Array.isArray(children) ? children[0] : children;
        const cls =
          child && typeof child === "object" && "props" in child
            ? String((child as { props: { className?: string } }).props.className ?? "")
            : "";
        if (cls.includes("language-mermaid")) {
          const code = extractText(children).trim();
          return <MermaidGraph code={code} title="diagrama" className="not-prose my-3" />;
        }
        return <pre>{children}</pre>;
      },
      a: ({ href, children }: { href?: string; children?: ReactNode }) => (
        <a href={href} target="_blank" rel="noreferrer noopener">
          {children}
        </a>
      ),
    }),
    [onCitationClick, citationCount],
  );
  return (
    <div className={cn("md", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
