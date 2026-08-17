"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type DocumentSummary = {
  id: string;
  original_filename: string;
  source_type: string;
  status: string;
  created_at: string;
};

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);

  useEffect(() => {
    fetch("http://localhost:8000/documents?status=pending_approval")
      .then((res) => res.json())
      .then((data) => setDocuments(data));
  }, []);

  return (
    <div className="min-h-screen bg-slate-100 p-8">
      <h1 className="mb-6 text-2xl font-bold">Onay Bekleyen Belgeler</h1>

      {documents.length === 0 && (
        <p className="text-slate-500">Onay bekleyen belge yok.</p>
      )}

      <div className="flex flex-col gap-4">
        {documents.map((doc) => (
          <Link key={doc.id} href={`/documents/${doc.id}`}>
            <Card className="hover:bg-slate-50">
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-base">
                  {doc.original_filename}
                  <Badge>{doc.source_type}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-slate-500">
                {new Date(doc.created_at).toLocaleString("tr-TR")}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}