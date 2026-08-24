"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type DocumentSummary = {
  id: string;
  original_filename: string;
  source_type: string;
  status: string;
  created_at: string;
};

const FILTERS = [
  { label: "Tümü", value: null },
  { label: "Onay Bekliyor", value: "pending_approval" },
  { label: "Onaylanmış", value: "approved" },
];

function statusBadgeVariant(status: string) {
  if (status === "approved") return "default";
  if (status === "pending_approval") return "secondary";
  return "outline";
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    const url = activeFilter
      ? `http://localhost:8000/documents?status=${activeFilter}`
      : "http://localhost:8000/documents";

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("Belgeler yüklenemedi");
        return res.json();
      })
      .then((data) => setDocuments(data))
      .catch(() => setError("Backend'e bağlanılamadı. Sunucunun çalıştığından emin olun."));
  }, [activeFilter]);

  return (
    <div className="min-h-screen bg-slate-100 p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Belge Yönetimi</h1>
        <Link href="/documents/upload">
          <Button>+ Yeni Belge Yükle</Button>
        </Link>
      </div>

      <div className="mb-6 flex gap-2">
        {FILTERS.map((f) => (
          <Button
            key={f.label}
            variant={activeFilter === f.value ? "default" : "outline"}
            onClick={() => setActiveFilter(f.value)}
          >
            {f.label}
          </Button>
        ))}
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {documents.length === 0 && (
        <p className="text-slate-500">Bu filtrede belge yok.</p>
      )}

      <div className="flex flex-col gap-4">
        {documents.map((doc) => (
          <Link key={doc.id} href={`/documents/${doc.id}`}>
            <Card className="hover:bg-slate-50">
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-base">
                  {doc.original_filename}
                  <div className="flex gap-2">
                    <Badge variant="outline">{doc.source_type}</Badge>
                    <Badge variant={statusBadgeVariant(doc.status)}>{doc.status}</Badge>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-slate-500">
                {new Date(doc.created_at).toLocaleString("tr-TR")}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}