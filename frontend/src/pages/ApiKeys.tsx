import { useEffect, useState, type FormEvent } from "react";
import { Check, Copy, KeyRound, Loader2, Trash2 } from "lucide-react";
import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { ApiKeySummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { formatDateTime } from "@/lib/utils";

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [revealedKey, setRevealedKey] = useState<string | null>(null);

  async function refresh() {
    try {
      setError(null);
      setKeys(await api.listKeys());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load API keys.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleRevoke(id: string) {
    if (!confirm("Revoke this API key? Requests using it will stop working immediately.")) return;
    try {
      await api.revokeKey(id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to revoke key.");
    }
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">API Keys</h1>
          <p className="text-sm text-muted-foreground">Use these keys to call the API from your own applications.</p>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <KeyRound className="mr-2 h-4 w-4" />
              New key
            </Button>
          </DialogTrigger>
          <CreateKeyDialog
            onCreated={(fullKey) => {
              setCreateOpen(false);
              setRevealedKey(fullKey);
              refresh();
            }}
          />
        </Dialog>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {keys === null ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading...
        </div>
      ) : keys.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-sm text-muted-foreground">No API keys yet.</CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Prefix</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last used</TableHead>
                <TableHead>Created</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id}>
                  <TableCell className="font-medium">{k.name}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{k.prefix}...</TableCell>
                  <TableCell>
                    <Badge variant={k.is_active ? "success" : "secondary"}>{k.is_active ? "Active" : "Revoked"}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {k.last_used_at ? formatDateTime(k.last_used_at) : "Never"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{formatDateTime(k.created_at)}</TableCell>
                  <TableCell>
                    {k.is_active && (
                      <button
                        onClick={() => handleRevoke(k.id)}
                        className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        aria-label={`Revoke ${k.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <Dialog open={!!revealedKey} onOpenChange={(open) => !open && setRevealedKey(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Your new API key</DialogTitle>
            <DialogDescription>
              Copy this now - for your security, it will never be shown again.
            </DialogDescription>
          </DialogHeader>
          {revealedKey && <CopyableKey value={revealedKey} />}
          <DialogFooter>
            <Button onClick={() => setRevealedKey(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CopyableKey({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-secondary p-3">
      <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-sm">{value}</code>
      <Button variant="outline" size="icon" onClick={handleCopy} aria-label="Copy key">
        {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
      </Button>
    </div>
  );
}

function CreateKeyDialog({ onCreated }: { onCreated: (fullKey: string) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await api.createKey(name);
      setName("");
      onCreated(result.full_key);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create key.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Create an API key</DialogTitle>
        <DialogDescription>Give it a name so you can recognize where it's used.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="space-y-2">
          <Label htmlFor="key-name">Name</Label>
          <Input id="key-name" required placeholder="e.g. production-server" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <DialogFooter>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating..." : "Create key"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
