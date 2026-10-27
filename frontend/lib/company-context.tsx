"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { apiFetch, errorMessage } from "@/lib/api";

export type Company = {
  id: string;
  name: string;
  email_domain: string;
};

type CompanyState = {
  companies: Company[];
  selectedId: string | null;
  loading: boolean;
  error: string | null;
};

type CompanyContextValue = CompanyState & {
  selected: Company | null;
  select: (id: string) => void;
  refresh: () => Promise<void>;
};

// Seçim tarayıcıda hatırlanır; sayfa yenilense de aynı şirket seçili kalır.
const STORAGE_KEY = "ik-asistan.company_id";

const CompanyContext = createContext<CompanyContextValue | null>(null);

function readStoredId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeId(id: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // localStorage kapalıysa (gizli pencere vb.) seçim yalnızca bu oturumda yaşar
  }
}

export function CompanyProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CompanyState>({
    companies: [],
    selectedId: null,
    loading: true,
    error: null,
  });

  const refresh = useCallback(async () => {
    try {
      const companies = await apiFetch<Company[]>("/companies");
      const stored = readStoredId();
      const selectedId = companies.some((c) => c.id === stored) ? stored : (companies[0]?.id ?? null);
      setState({ companies, selectedId, loading: false, error: null });
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: errorMessage(err) }));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const select = useCallback((id: string) => {
    storeId(id);
    setState((s) => ({ ...s, selectedId: id }));
  }, []);

  const selected = state.companies.find((c) => c.id === state.selectedId) ?? null;

  return (
    <CompanyContext.Provider value={{ ...state, selected, select, refresh }}>
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompany(): CompanyContextValue {
  const ctx = useContext(CompanyContext);
  if (!ctx) {
    throw new Error("useCompany yalnızca CompanyProvider içinde kullanılabilir");
  }
  return ctx;
}
