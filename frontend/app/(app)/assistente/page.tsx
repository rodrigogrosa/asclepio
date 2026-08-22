import type { Metadata } from "next";
import { Suspense } from "react";
import { ChatView } from "@/components/chat/chat-view";
import { RequirePermission } from "@/components/layout/guard";

export const metadata: Metadata = { title: "Assistente" };

export default function AssistentePage() {
  return (
    <Suspense fallback={null}>
      <RequirePermission perms="assistant:chat"><ChatView /></RequirePermission>
    </Suspense>
  );
}
