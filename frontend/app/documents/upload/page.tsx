"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TEST_COMPANY_ID = "4d3ef371-7d0e-4111-91d0-aa8ffe7e0188";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [quality, setQuality] = useState<string>("clean");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isPdf = file?.name.toLowerCase().endsWith(".pdf");

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("company_id", TEST_COMPANY_ID);
    if (!isPdf) {
      formData.append("document_quality", quality);
    }

    try {
      const res = await fetch("http://localhost:8000/documents/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Yükleme başarısız oldu");
      }

      router.push("/documents");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Beklenmeyen bir hata oluştu");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 p-8">
      <h1 className="mb-6 text-2xl font-bold">Yeni Belge Yükle</h1>

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle className="text-base">Belge Seç</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <input
            type="file"
            accept=".jpg,.jpeg,.png,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm"
          />

          {file && !isPdf && (
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">Belge Kalitesi</label>
              <select
                value={quality}
                onChange={(e) => setQuality(e.target.value)}
                className="rounded border border-slate-200 p-2 text-sm"
              >
                <option value="clean">Temiz (düz taranmış belge)</option>
                <option value="complex">Karmaşık (fotoğraf, eğik, gölgeli)</option>
              </select>
            </div>
          )}

          {file && isPdf && (
            <p className="text-sm text-slate-500">
              PDF dosyaları otomatik olarak metin katmanından işlenir, kalite seçimi gerekmez.
            </p>
          )}

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <Button onClick={handleUpload} disabled={!file || uploading}>
            {uploading ? "Yükleniyor..." : "Yükle"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
