"use client";

import { useCompany } from "@/lib/company-context";

export function CompanySelect() {
  const { companies, selectedId, select, loading, error } = useCompany();

  if (loading) {
    return <span className="text-sm text-slate-400">Şirketler yükleniyor...</span>;
  }
  if (error) {
    return <span className="text-sm text-red-600">Şirketler alınamadı</span>;
  }
  if (companies.length === 0) {
    return <span className="text-sm text-amber-700">Kayıtlı şirket yok</span>;
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-slate-500">Şirket</span>
      <select
        value={selectedId ?? ""}
        onChange={(e) => select(e.target.value)}
        className="rounded border border-slate-200 bg-white px-2 py-1 text-sm"
      >
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} ({c.email_domain})
          </option>
        ))}
      </select>
    </label>
  );
}
