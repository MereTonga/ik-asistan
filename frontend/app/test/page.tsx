"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiFetch, errorMessage } from "@/lib/api";
import { useCompany } from "@/lib/company-context";

type Scenario = {
  sender: string;
  subject: string;
  body: string;
};

type SimulationResult = {
  status: string;
  reason?: string;
  answer?: string;
  was_escalated?: boolean;
  error?: string; // istek seviyesinde hata (ağ, 4xx) — UI'da gösterilir
};

export default function TestPanel() {
  const { selected, loading: companyLoading } = useCompany();
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [results, setResults] = useState<Record<number, SimulationResult>>({});
  const [loadingIndex, setLoadingIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Scenario[]>("/test/scenarios")
      .then((data) => {
        setScenarios(data);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  const handleSimulate = async (index: number) => {
    if (!selected) return;
    setLoadingIndex(index);
    try {
      const data = await apiFetch<SimulationResult>(
        `/test/simulate/${index}?company_id=${selected.id}`,
        { method: "POST" }
      );
      setResults((prev) => ({ ...prev, [index]: data }));
    } catch (err) {
      setResults((prev) => ({ ...prev, [index]: { status: "error", error: errorMessage(err) } }));
    } finally {
      setLoadingIndex(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      <h1 className="mb-2 text-2xl font-bold">Test Paneli — Senaryo Simülasyonu</h1>
      <p className="mb-6 text-sm text-slate-500">
        Senaryolar {selected ? <strong>{selected.name}</strong> : "seçili şirket"} için çalışır; simülasyon hiçbir
        zaman gerçek e-posta göndermez.
      </p>

      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-600">{error}</div>
      )}

      {!companyLoading && !selected && (
        <p className="mb-4 text-sm text-amber-700">Önce sağ üstten bir şirket seçin.</p>
      )}

      {!error && scenarios === null && <p className="text-slate-500">Yükleniyor...</p>}

      <div className="flex flex-col gap-4">
        {scenarios?.map((scenario, index) => {
          const result = results[index];
          return (
            <Card key={index}>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
                  {scenario.subject}
                  <span className="text-sm font-normal text-slate-400">{scenario.sender}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <p className="text-sm text-slate-600">{scenario.body}</p>

                <Button
                  variant="outline"
                  onClick={() => handleSimulate(index)}
                  disabled={loadingIndex !== null || !selected}
                >
                  {loadingIndex === index ? "Çalışıyor..." : "Bu Senaryoyu Çalıştır"}
                </Button>

                {result && (
                  <div className="rounded border border-slate-200 p-3">
                    {result.status === "error" ? (
                      <Badge variant="destructive">Hata: {result.error}</Badge>
                    ) : result.status === "skipped" ? (
                      <Badge variant="secondary">Atlandı: {result.reason}</Badge>
                    ) : (
                      <>
                        <Badge variant={result.was_escalated ? "destructive" : "default"}>
                          {result.was_escalated ? "Yönlendirildi" : "Cevaplandı"}
                        </Badge>
                        <p className="mt-2 whitespace-pre-wrap text-sm">{result.answer}</p>
                      </>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
