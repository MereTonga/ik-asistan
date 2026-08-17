"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function Home() {
  const [status, setStatus] = useState<string>("Kontrol ediliyor...");

  useEffect(() => {
    fetch("http://localhost:8000/health")
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus("Bağlantı hatası"));
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <Card className="w-96">
        <CardHeader>
          <CardTitle>Backend Bağlantı Testi</CardTitle>
        </CardHeader>
        <CardContent>
          <Badge variant={status === "healthy" ? "default" : "destructive"}>
            {status}
          </Badge>
        </CardContent>
      </Card>
    </div>
  );
}