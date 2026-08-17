import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <Card className="w-96">
        <CardHeader>
          <CardTitle>shadcn Test Kartı</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Badge>Onay Bekliyor</Badge>
          <Button>Onayla</Button>
        </CardContent>
      </Card>
    </div>
  );
}