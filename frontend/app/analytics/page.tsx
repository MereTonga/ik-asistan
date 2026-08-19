"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

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

const TEST_COMPANY_ID = "4d3ef371-7d0e-4111-91d0-aa8ffe7e0188";

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    fetch(`http://localhost:8000/analytics/summary?company_id=${TEST_COMPANY_ID}`)
      .then((res) => res.json())
      .then((data) => setSummary(data));
  }, []);

  if (!summary) {
    return <div className="p-8">Yükleniyor...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-100 p-8">
      <h1 className="mb-6 text-2xl font-bold">Analitik</h1>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-slate-500">Toplam Soru</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold">
            {summary.total_questions}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-slate-500">Yönlendirilen</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold">
            {summary.escalated_count}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-slate-500">Yönlendirme Oranı</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold">
            %{Math.round(summary.escalation_rate * 100)}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            En Çok Yönlendirilen Konular (Dokümantasyon Eksikleri)
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {summary.top_escalated_topics.length === 0 && (
            <p className="text-sm text-slate-500">Henüz yönlendirilen konu yok.</p>
          )}
          {summary.top_escalated_topics.map((topic) => (
            <div
              key={topic.subject}
              className="flex items-center justify-between border-b border-slate-100 py-2"
            >
              <span className="text-sm">{topic.subject}</span>
              <Badge variant="secondary">{topic.count}x</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
