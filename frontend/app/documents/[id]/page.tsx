"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type DocumentDetail = {
  id: string;
  original_filename: string;
  stored_filename: string;
  source_type: string;
  status: string;
  raw_extracted_text: string;
  created_at: string;
};

export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [approving, setApproving] = useState(false);
  const [editedText, setEditedText] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`http://localhost:8000/documents/${id}`)
      .then((res) => res.json())
      .then((data) => {
        setDoc(data);
        setEditedText(data.raw_extracted_text);
      });
  }, [id]);

  const handleSave = async () => {
    setSaving(true);
    await fetch(`http://localhost:8000/documents/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_extracted_text: editedText }),
    });
    setSaving(false);
  };

  const handleApprove = async () => {
    setApproving(true);
    await fetch(`http://localhost:8000/documents/${id}/approve`, {
      method: "POST",
    });
    router.push("/documents");
  };

  if (!doc) {
    return <div className="p-8">Yükleniyor...</div>;
  }

  const isImage = doc.source_type === "ocr_clean" || doc.source_type === "ocr_complex";
  const originalFileUrl = `http://localhost:8000/uploads/${doc.stored_filename}`;

  return (
    <div className="min-h-screen bg-slate-100 p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">{doc.original_filename}</h1>
        <Badge>{doc.status}</Badge>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Orijinal Belge</CardTitle>
          </CardHeader>
          <CardContent>
            {isImage ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={originalFileUrl} alt="Orijinal belge" className="w-full rounded" />
            ) : (
              <p className="text-slate-500">Bu belge türü için önizleme yok.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">OCR / Çıkarılan Metin</CardTitle>
          </CardHeader>
          <CardContent>
            <textarea
              value={editedText}
              onChange={(e) => setEditedText(e.target.value)}
              disabled={doc.status === "approved"}
              className="h-96 w-full whitespace-pre-wrap rounded border border-slate-200 p-3 text-sm"
            />
          </CardContent>
        </Card>
      </div>

      {doc.status === "pending_approval" && (
        <div className="mt-6 flex gap-3">
          <Button variant="outline" onClick={handleSave} disabled={saving}>
            {saving ? "Kaydediliyor..." : "Kaydet"}
          </Button>
          <Button onClick={handleApprove} disabled={approving}>
            {approving ? "Onaylanıyor..." : "Onayla"}
          </Button>
        </div>
      )}
    </div>
  );
}
