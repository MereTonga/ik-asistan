// Backend'deki DocumentStatus değerlerinin kullanıcıya gösterilen karşılıkları.
export const STATUS_LABELS: Record<string, string> = {
  processing: "İşleniyor",
  pending_approval: "Onay bekliyor",
  failed: "Hatalı",
  indexing: "İndeksleniyor",
  approved: "Onaylı",
  retired: "Emekli",
};

export const SOURCE_LABELS: Record<string, string> = {
  pending: "Bekliyor",
  pdf_text: "PDF metin",
  ocr_clean: "OCR (temiz)",
  ocr_complex: "OCR (karmaşık)",
  seed_markdown: "Örnek veri",
};

// Bu durumlarda worker çalışıyordur; sayfa kendini periyodik olarak yeniler.
export const BUSY_STATUSES = ["processing", "indexing"];

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

export function statusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "approved") return "default";
  if (status === "pending_approval") return "secondary";
  if (status === "failed") return "destructive";
  return "outline";
}
