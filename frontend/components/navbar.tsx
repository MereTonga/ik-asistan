"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CompanySelect } from "@/components/company-select";

const NAV_ITEMS = [
  { label: "Ana Sayfa", href: "/" },
  { label: "Belgeler", href: "/documents" },
  { label: "Test Paneli", href: "/test" },
  { label: "Analitik", href: "/analytics" },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <nav className="border-b border-slate-200 bg-white px-4 py-4 md:px-8">
      <div className="flex flex-wrap items-center gap-6">
        <Link href="/" className="font-bold">
          İK Asistanı
        </Link>
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={
                isActive
                  ? "text-sm font-semibold text-slate-900"
                  : "text-sm text-slate-500 hover:text-slate-900"
              }
            >
              {item.label}
            </Link>
          );
        })}
        <div className="ml-auto">
          <CompanySelect />
        </div>
      </div>
    </nav>
  );
}
