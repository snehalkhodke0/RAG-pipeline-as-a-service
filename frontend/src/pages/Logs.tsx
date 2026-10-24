import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { QueryLogEntry, UsageTotals } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime } from "@/lib/utils";

export function LogsPage() {
  const [logs, setLogs] = useState<QueryLogEntry[] | null>(null);
  const [usage, setUsage] = useState<UsageTotals | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getLogs(50), api.getUsage()])
      .then(([logsData, usageData]) => {
        setLogs(logsData);
        setUsage(usageData);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load logs."));
  }, []);

  return (
    <div>
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Logs & Usage</h1>
      <p className="mb-6 text-sm text-muted-foreground">Recent queries and per-key usage totals.</p>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {usage && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <UsageStat label="Queries" value={usage.queries} />
          <UsageStat label="Prompt tokens" value={usage.prompt_tokens} />
          <UsageStat label="Completion tokens" value={usage.completion_tokens} />
          <UsageStat label="Documents / Chunks" value={`${usage.documents} / ${usage.chunks}`} />
        </div>
      )}

      {logs === null ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading...
        </div>
      ) : logs.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-sm text-muted-foreground">No queries logged yet.</CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Query</TableHead>
                <TableHead>Chunks</TableHead>
                <TableHead>Retrieval</TableHead>
                <TableHead>LLM</TableHead>
                <TableHead>Total</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.map((log) => (
                <TableRow key={log.id}>
                  <TableCell className="max-w-sm truncate">{log.query}</TableCell>
                  <TableCell>{log.chunks_retrieved ?? "-"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{log.retrieval_ms ?? "-"} ms</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{log.llm_ms ?? "-"} ms</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{log.total_ms ?? "-"} ms</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{formatDateTime(log.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

function UsageStat({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 text-xs text-muted-foreground">{label}</CardContent>
    </Card>
  );
}
