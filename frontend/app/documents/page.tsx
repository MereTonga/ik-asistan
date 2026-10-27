"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch, errorMessage } from "@/lib/api";
import { useCompany } from "@/lib/company-context";
import { sourceLabel, statusBadgeVariant, statusLabel } from "@/lib/status";

type DocumentSummary = {
  id: string;
  original_filename: string;
  source_type: string;
  status: string;
  error_message: string | null;
  created_at: string;
};

type LoadResult = {
  key: string; // hangi şirket + filtre için yüklendi (eski sonuç yeni seçimle karışmasın)
  items: DocumentSummary[];
};

const FILTERS: { label: string; value: string | null }[] = [
  { label: "Tümü", value: null },
  { label: "İşleniyor", value: "processing" },
  { label: "Onay bekliyor", value: "pending_approval" },
  { label: "İndeksleniyor", value: "indexing" },
  { label: "Hatalı", value: "failed" },
  { label: "Onaylı", value: "approved" },
];

export default function DocumentsPage() {
  const { selectedId, loading: companyLoading } = useCompany();
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [result, setResult] = useState<LoadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadKey = `${selectedId ?? ""}|${activeFilter ?? ""}`;

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    const params = new URLSearchParams({ company_id: selectedId });
    if (activeFilter) params.set("status", activeFilter);

    apiFetch<DocumentSummary[]>(`/documents?${params.toString()}`)
      .then((items) => {
        if (cancelled) return;
        setResult({ key: loadKey, items });
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId, activeFilter, loadKey]);

  const documents = result && result.key === loadKey ? result.items : null;
  const isLoading = !error && documents === null && (companyLoading || !!selectedId);

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Belge Yönetimi</h1>
        <Link href="/documents/upload">
          <Button>+ Yeni Belge Yükle</Button>
        </Link>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
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

      {!companyLoading && !selectedId && (
        <p className="text-slate-500">Önce bir şirket seçin (sağ üst köşe).</p>
      )}

      {isLoading && <p className="text-slate-500">Yükleniyor...</p>}

      {documents && documents.length === 0 && (
        <p className="text-slate-500">Bu filtrede belge yok.</p>
      )}

      <div className="flex flex-col gap-4">
        {documents?.map((doc) => (
          <Link key={doc.id} href={`/documents/${doc.id}`}>
            <Card className="hover:bg-slate-50">
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
                  {doc.original_filename}
                  <div className="flex gap-2">
                    <Badge variant="outline">{sourceLabel(doc.source_type)}</Badge>
                    <Badge variant={statusBadgeVariant(doc.status)}>{statusLabel(doc.status)}</Badge>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-slate-500">
                {new Date(doc.created_at).toLocaleString("tr-TR")}
                {doc.status === "failed" && doc.error_message && (
                  <p className="mt-1 text-red-600">{doc.error_message}</p>
                )}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
