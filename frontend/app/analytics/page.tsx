"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiFetch, errorMessage } from "@/lib/api";
import { useCompany } from "@/lib/company-context";

type Topic = {
  subject: string;
  count: number;
};

type Summary = {
  total_questions: number;
  escalated_count: number;
  escalation_rate: number;
  top_escalated_topics: Topic[];
};

type LoadResult = { companyId: string; summary: Summary };

export default function AnalyticsPage() {
  const { selected, loading: companyLoading } = useCompany();
  const [result, setResult] = useState<LoadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const companyId = selected?.id ?? null;

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    apiFetch<Summary>(`/analytics/summary?company_id=${companyId}`)
      .then((summary) => {
        if (cancelled) return;
        setResult({ companyId, summary });
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  if (error) {
    return (
      <div className="p-8">
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-600">{error}</div>
      </div>
    );
  }

  if (!companyLoading && !companyId) {
    return <div className="p-8 text-sm text-amber-700">Önce sağ üstten bir şirket seçin.</div>;
  }

  const summary = result && result.companyId === companyId ? result.summary : null;
  if (!summary) {
    return <div className="p-8">Yükleniyor...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      <h1 className="mb-1 text-2xl font-bold">Analitik</h1>
      <p className="mb-6 text-sm text-slate-500">{selected?.name}</p>

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-slate-500">Toplam Soru</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold">{summary.total_questions}</CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-slate-500">Yönlendirilen</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold">{summary.escalated_count}</CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-slate-500">Yönlendirme Oranı</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold">%{Math.round(summary.escalation_rate * 100)}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">En Çok Yönlendirilen Konular (Dokümantasyon Eksikleri)</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {summary.top_escalated_topics.length === 0 && (
            <p className="text-sm text-slate-500">Henüz yönlendirilen konu yok.</p>
          )}
          {summary.top_escalated_topics.map((topic) => (
            <div key={topic.subject} className="flex items-center justify-between border-b border-slate-100 py-2">
              <span className="text-sm">{topic.subject}</span>
              <Badge variant="secondary">{topic.count}x</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
