"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch, errorMessage } from "@/lib/api";
import { useCompany } from "@/lib/company-context";

export default function UploadPage() {
  const router = useRouter();
  const { selected, loading: companyLoading } = useCompany();
  const [file, setFile] = useState<File | null>(null);
  const [quality, setQuality] = useState<string>("clean");
  const [visibility, setVisibility] = useState<"internal" | "public">("internal");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isPdf = file?.name.toLowerCase().endsWith(".pdf");

  const handleUpload = async () => {
    if (!file || !selected) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("company_id", selected.id);
    formData.append("visibility", visibility);
    if (!isPdf) {
      formData.append("document_quality", quality);
    }

    try {
      await apiFetch("/documents/upload", { method: "POST", body: formData });
      router.push("/documents");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      <h1 className="mb-6 text-2xl font-bold">Yeni Belge Yükle</h1>

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle className="text-base">
            Belge Seç{selected ? ` — ${selected.name}` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {!companyLoading && !selected && (
            <p className="text-sm text-amber-700">Yükleme için önce sağ üstten bir şirket seçin.</p>
          )}

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

          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">Görünürlük</legend>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name="visibility"
                value="internal"
                checked={visibility === "internal"}
                onChange={() => setVisibility("internal")}
                className="mt-1"
              />
              <span>
                <strong>Şirket içi</strong> — yalnızca şirket çalışanlarının sorularına kaynak olur (varsayılan)
              </span>
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name="visibility"
                value="public"
                checked={visibility === "public"}
                onChange={() => setVisibility("public")}
                className="mt-1"
              />
              <span>
                <strong>Herkese açık</strong> — dışarıdan yazanlara da (adaylar vb.) cevap kaynağı olur
              </span>
            </label>
          </fieldset>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <Button onClick={handleUpload} disabled={!file || !selected || uploading}>
            {uploading ? "Yükleniyor..." : "Yükle"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
