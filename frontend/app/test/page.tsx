"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiFetch, errorMessage } from "@/lib/api";
import { type Company, useCompany } from "@/lib/company-context";

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
  external?: boolean; // dışarıdan gelen gibi çalıştırıldı
  question?: string; // gönderilen soru (takip sorusunda farklıdır)
  is_follow_up?: boolean;
  error?: string; // istek seviyesinde hata (ağ, 4xx) — UI'da gösterilir
};

// Sonuçlar bu bileşenin state'inde yaşar; üst bileşen şirket değişince `key` ile yeniden
// kurar, böylece A şirketinin cevabı B şirketi seçiliyken ekranda kalmaz.
function ScenarioRunner({ scenarios, company }: { scenarios: Scenario[]; company: Company }) {
  const [results, setResults] = useState<Record<number, SimulationResult[]>>({});
  const [followUps, setFollowUps] = useState<Record<number, string>>({});
  const [loadingIndex, setLoadingIndex] = useState<number | null>(null);
  const [external, setExternal] = useState(false);

  const run = async (index: number, question?: string) => {
    setLoadingIndex(index);
    try {
      const data = await apiFetch<SimulationResult>(
        `/test/simulate/${index}?company_id=${company.id}&external=${external}`,
        question
          ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) }
          : { method: "POST" }
      );
      setResults((prev) => ({ ...prev, [index]: [...(prev[index] ?? []), data] }));
      if (question) setFollowUps((prev) => ({ ...prev, [index]: "" }));
    } catch (err) {
      setResults((prev) => ({
        ...prev,
        [index]: [...(prev[index] ?? []), { status: "error", error: errorMessage(err), question }],
      }));
    } finally {
      setLoadingIndex(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <label className="flex items-start gap-2 rounded border border-slate-200 bg-white p-3 text-sm">
        <input type="checkbox" checked={external} onChange={(e) => setExternal(e.target.checked)} className="mt-1" />
        <span>
          <strong>Dışarıdan gelen gibi çalıştır.</strong> Gönderen şirket çalışanı değilmiş gibi davranılır: yalnızca
          &quot;Herkese açık&quot; belgeler kullanılır, şirket içi politikalar görünmez.
        </span>
      </label>
      {scenarios.map((scenario, index) => {
        const chain = results[index] ?? [];
        const followUp = followUps[index] ?? "";
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
                onClick={() => run(index)}
                disabled={loadingIndex !== null}
              >
                {loadingIndex === index ? "Çalışıyor..." : "Bu Senaryoyu Çalıştır"}
              </Button>

              {chain.map((result, i) => (
                <div key={i} className="rounded border border-slate-200 p-3">
                  {result.is_follow_up && result.question && (
                    <p className="mb-2 text-sm text-slate-500">
                      <span className="font-medium">Takip sorusu:</span> {result.question}
                    </p>
                  )}
                  {result.status === "error" ? (
                    <Badge variant="destructive">Hata: {result.error}</Badge>
                  ) : result.status === "skipped" ? (
                    <Badge variant="secondary">Atlandı: {result.reason}</Badge>
                  ) : (
                    <>
                      <Badge variant={result.was_escalated ? "destructive" : "default"}>
                        {result.was_escalated ? "Yönlendirildi" : "Cevaplandı"}
                      </Badge>
                      {result.external && (
                        <Badge variant="secondary" className="ml-2">dış gönderen</Badge>
                      )}
                      <p className="mt-2 whitespace-pre-wrap text-sm">{result.answer}</p>
                    </>
                  )}
                </div>
              ))}

              {chain.some((r) => r.status === "processed") && (
                <div className="flex flex-col gap-2 rounded border border-dashed border-slate-300 p-3">
                  <label className="text-sm font-medium">Takip sorusu (aynı yazışmaya bağlanır, hafıza devreye girer)</label>
                  <textarea
                    value={followUp}
                    onChange={(e) => setFollowUps((prev) => ({ ...prev, [index]: e.target.value }))}
                    placeholder="Örn: Peki ya cuma günleri?"
                    className="h-20 w-full rounded border border-slate-200 p-2 text-sm"
                  />
                  <div>
                    <Button
                      variant="outline"
                      onClick={() => run(index, followUp.trim())}
                      disabled={loadingIndex !== null || followUp.trim().length === 0}
                    >
                      {loadingIndex === index ? "Çalışıyor..." : "Takip sorusunu gönder"}
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export default function TestPanel() {
  const { selected, loading: companyLoading } = useCompany();
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Scenario[]>("/test/scenarios")
      .then((data) => {
        setScenarios(data);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      <h1 className="mb-2 text-2xl font-bold">Test Paneli — Senaryo Simülasyonu</h1>
      <p className="mb-6 text-sm text-slate-500">
        Senaryolar {selected ? <strong>{selected.name}</strong> : "seçili şirket"} için çalışır; simülasyon hiçbir
        zaman gerçek e-posta göndermez. Şirket değiştiğinde sonuçlar sıfırlanır.
      </p>

      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-600">{error}</div>
      )}

      {!companyLoading && !selected && (
        <p className="mb-4 text-sm text-amber-700">Önce sağ üstten bir şirket seçin.</p>
      )}

      {!error && scenarios === null && <p className="text-slate-500">Yükleniyor...</p>}

      {scenarios && selected && (
        <ScenarioRunner key={selected.id} scenarios={scenarios} company={selected} />
      )}
    </div>
  );
}
