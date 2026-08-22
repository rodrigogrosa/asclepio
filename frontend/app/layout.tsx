import type { Metadata, Viewport } from "next";
import { Inter, Montserrat } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/providers/auth-provider";
import { ToastProvider } from "@/components/providers/toast-provider";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const montserrat = Montserrat({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-montserrat",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Asclépio — Assistente Clínico Inteligente", template: "%s · Asclépio" },
  description:
    "Assistente clínico com LLM fine-tunada, RAG e LangGraph. Hospital Universitário FIAP (fictício) · Tech Challenge 8IADT · Fase 3.",
  icons: { icon: "/brand/asclepio-mark.svg", apple: "/brand/asclepio-mark.svg" },
  applicationName: "Asclépio",
};

export const viewport: Viewport = {
  themeColor: "#0B0B10",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR" className={`${inter.variable} ${montserrat.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-bg text-text">
        <AuthProvider>
          <ToastProvider>{children}</ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
