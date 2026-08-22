import type { Metadata } from "next";
import { Suspense } from "react";
import { ChatView } from "@/components/chat/chat-view";

export const metadata: Metadata = { title: "Assistente" };

export default function AssistentePage() {
  return (
    <Suspense fallback={null}>
      <ChatView />
    </Suspense>
  );
}
