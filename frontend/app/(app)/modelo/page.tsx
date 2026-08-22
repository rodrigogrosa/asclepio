import type { Metadata } from "next";
import { ModelView } from "@/components/model/model-view";

export const metadata: Metadata = { title: "Modelo" };

export default function ModeloPage() {
  return <ModelView />;
}
