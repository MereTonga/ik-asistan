"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

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
};

const TEST_COMPANY_ID = "4d3ef371-7d0e-4111-91d0-aa8ffe7e0188";

export default function TestPanel() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [results, setResults] = useState<Record<number, SimulationResult>>({});
  const [loadingIndex, setLoadingIndex] = useState<number | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/test/scenarios")
      .then((res) => res.json())
      .then((data) => setScenarios(data));
  }, []);

  const handleSimulate = async (index: number) => {
    setLoadingIndex(index);
    const res = await fetch(
      `http://localhost:8000/test/simulate/${index}?company_id=${TEST_COMPANY_ID}`,
      { method: "POST" }
    );
    const data = await res.json();
    setResults((prev) => ({ ...prev, [index]: data }));
    setLoadingIndex(null);
  };

  return (
    <div className="min-h-screen bg-slate-100 p-8">
      <h1 className="mb-6 text-2xl font-bold">Test Paneli — Senaryo Simülasyonu</h1>

      <div className="flex flex-col gap-4">
        {scenarios.map((scenario, index) => {
          const result = results[index];
          return (
            <Card key={index}>
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-base">
                  {scenario.subject}
                  <span className="text-sm font-normal text-slate-400">
                    {scenario.sender}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <p className="text-sm text-slate-600">{scenario.body}</p>

                <Button
                  variant="outline"
                  onClick={() => handleSimulate(index)}
                  disabled={loadingIndex === index}
                >
                  {loadingIndex === index ? "Çalışıyor..." : "Bu Senaryoyu Çalıştır"}
                </Button>

                {result && (
                  <div className="rounded border border-slate-200 p-3">
                    {result.status === "skipped" ? (
                      <Badge variant="secondary">Atlandı: {result.reason}</Badge>
                    ) : (
                      <>
                        <Badge variant={result.was_escalated ? "destructive" : "default"}>
                          {result.was_escalated ? "Yönlendirildi" : "Cevaplandı"}
                        </Badge>
                        <p className="mt-2 text-sm">{result.answer}</p>
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
