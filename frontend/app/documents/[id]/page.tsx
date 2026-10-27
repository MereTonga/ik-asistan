"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { API_BASE, apiFetch, errorMessage } from "@/lib/api";
import { BUSY_STATUSES, sourceLabel, statusBadgeVariant, statusLabel } from "@/lib/status";

type DocumentDetail = {
  id: string;
  original_filename: string;
  stored_filename: string | null;
  source_type: string;
  document_quality: string | null;
  status: string;
  raw_extracted_text: string | null;
  error_message: string | null;
  created_at: string;
};

const POLL_INTERVAL_MS = 3000;
const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png"];

export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editedText, setEditedText] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // reloadTick her arttığında belge sunucudan yeniden okunur (ilk yükleme, periyodik yenileme, işlem sonrası).
  const [reloadTick, setReloadTick] = useState(0);
  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  // Metin alanı yalnızca ilk yüklemede ve durum değiştiğinde sunucudan doldurulur;
  // periyodik yenilemeler kullanıcının düzenlemesini ezmez.
  const lastStatusRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<DocumentDetail>(`/documents/${id}`)
      .then((data) => {
        if (cancelled) return;
        setDoc(data);
        setLoadError(null);
        if (lastStatusRef.current !== data.status) {
          lastStatusRef.current = data.status;
          setEditedText(data.raw_extracted_text ?? "");
        }
      })
      .catch((err) => {
        if (!cancelled) setLoadError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [id, reloadTick]);

  const isBusy = !!doc && BUSY_STATUSES.includes(doc.status);

  useEffect(() => {
    if (!isBusy) return;
    const timer = window.setInterval(reload, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [isBusy, reload]);

  const runAction = async (name: string, fn: () => Promise<unknown>, successMessage?: string) => {
    setBusyAction(name);
    setActionError(null);
    setInfo(null);
    try {
      await fn();
      if (successMessage) setInfo(successMessage);
      reload();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusyAction(null);
    }
  };

  const handleSave = () =>
    runAction(
      "save",
      () =>
        apiFetch(`/documents/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ raw_extracted_text: editedText }),
        }),
      "Metin kaydedildi."
    );

  const handleApprove = () =>
    runAction("approve", async () => {
      if (editedText !== (doc?.raw_extracted_text ?? "")) {
        // Onaydan önce ekrandaki düzenleme kaydedilsin; aksi halde eski metin indekslenir
        await apiFetch(`/documents/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ raw_extracted_text: editedText }),
        });
      }
      await apiFetch(`/documents/${id}/approve`, { method: "POST" });
    }, "Onay kuyruğa alındı; belge arka planda indeksleniyor.");

  const handleReprocess = () =>
    runAction("reprocess", () => apiFetch(`/documents/${id}/reprocess`, { method: "POST" }), "Belge yeniden işleniyor.");

  const handleRechunk = () =>
    runAction("rechunk", () => apiFetch(`/documents/${id}/rechunk`, { method: "POST" }), "Yeniden parçalama kuyruğa alındı.");

  if (loadError && !doc) {
    return (
      <div className="p-8">
        <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-600">{loadError}</div>
        <Button variant="outline" className="mt-4" onClick={() => router.push("/documents")}>
          Listeye dön
        </Button>
      </div>
    );
  }

  if (!doc) {
    return <div className="p-8">Yükleniyor...</div>;
  }

  const extension = (doc.stored_filename ?? "").toLowerCase().slice((doc.stored_filename ?? "").lastIndexOf("."));
  const isImage = IMAGE_EXTENSIONS.includes(extension);
  const originalFileUrl = doc.stored_filename ? `${API_BASE}/uploads/${doc.stored_filename}` : null;
  const canEdit = doc.status === "pending_approval";
  const textIsEmpty = editedText.trim().length === 0;

  return (
    <div className="min-h-screen bg-slate-100 p-4 md:p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{doc.original_filename}</h1>
        <div className="flex gap-2">
          <Badge variant="outline">{sourceLabel(doc.source_type)}</Badge>
          <Badge variant={statusBadgeVariant(doc.status)}>{statusLabel(doc.status)}</Badge>
        </div>
      </div>

      {isBusy && (
        <div className="mb-4 rounded border border-slate-200 bg-white p-3 text-sm text-slate-600">
          {statusLabel(doc.status)}... Bu sayfa birkaç saniyede bir kendini yeniler.
        </div>
      )}

      {doc.error_message && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-600">
          Son hata: {doc.error_message}
        </div>
      )}

      {actionError && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-600">{actionError}</div>
      )}

      {info && (
        <div className="mb-4 rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{info}</div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Orijinal Belge</CardTitle>
          </CardHeader>
          <CardContent>
            {isImage && originalFileUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={originalFileUrl} alt="Orijinal belge" className="w-full rounded" />
            ) : originalFileUrl ? (
              <p className="text-slate-500">
                Bu belge türü için önizleme yok.{" "}
                <a href={originalFileUrl} target="_blank" rel="noreferrer" className="underline">
                  Dosyayı aç
                </a>
              </p>
            ) : (
              <p className="text-slate-500">Dosya bulunamadı.</p>
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
              disabled={!canEdit}
              placeholder={isBusy ? "Metin hazırlanıyor..." : "Metin yok"}
              className="h-96 w-full whitespace-pre-wrap rounded border border-slate-200 p-3 text-sm"
            />
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        {canEdit && (
          <>
            <Button variant="outline" onClick={handleSave} disabled={busyAction !== null}>
              {busyAction === "save" ? "Kaydediliyor..." : "Kaydet"}
            </Button>
            <Button onClick={handleApprove} disabled={busyAction !== null || textIsEmpty}>
              {busyAction === "approve" ? "Onaylanıyor..." : "Onayla"}
            </Button>
          </>
        )}
        {(doc.status === "failed" || doc.status === "pending_approval") && (
          <Button variant="outline" onClick={handleReprocess} disabled={busyAction !== null}>
            {busyAction === "reprocess" ? "Kuyruğa alınıyor..." : "Yeniden işle"}
          </Button>
        )}
        {doc.status === "approved" && (
          <Button variant="outline" onClick={handleRechunk} disabled={busyAction !== null}>
            {busyAction === "rechunk" ? "Kuyruğa alınıyor..." : "Yeniden parçala"}
          </Button>
        )}
      </div>
      {canEdit && textIsEmpty && (
        <p className="mt-2 text-sm text-amber-700">Metin boşken onaylanamaz; metni düzenleyin ya da belgeyi yeniden işleyin.</p>
      )}
    </div>
  );
}
