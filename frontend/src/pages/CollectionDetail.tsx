import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileText, Loader2, Trash2, UploadCloud } from "lucide-react";
import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { Collection, DocumentItem } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatBytes, formatDateTime } from "@/lib/utils";

const ACTIVE_STATUSES = new Set(["QUEUED", "PARSING", "CHUNKING", "EMBEDDING"]);

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "success" | "warning"> = {
  QUEUED: "secondary",
  PARSING: "warning",
  CHUNKING: "warning",
  EMBEDDING: "warning",
  READY: "success",
  FAILED: "destructive",
};

export function CollectionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [collection, setCollection] = useState<Collection | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [urlValue, setUrlValue] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!id) return;
    try {
      const [collectionData, documentsData] = await Promise.all([api.getCollection(id), api.listDocuments(id)]);
      setCollection(collectionData);
      setDocuments(documentsData);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load collection.");
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll while any document is still being processed, so the progress bars update live.
  useEffect(() => {
    const hasActive = documents?.some((d) => ACTIVE_STATUSES.has(d.status));
    if (!hasActive) return;

    pollRef.current = window.setInterval(refresh, 2000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [documents, refresh]);

  async function uploadFiles(files: FileList | File[]) {
    if (!id) return;
    setError(null);
    setIsUploading(true);
    try {
      for (const file of Array.from(files)) {
        await api.uploadDocument(id, file);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleUrlSubmit() {
    if (!id || !urlValue.trim()) return;
    setError(null);
    setIsUploading(true);
    try {
      await api.uploadDocumentUrl(id, urlValue.trim());
      setUrlValue("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to fetch URL.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleDelete(documentId: string) {
    if (!confirm("Delete this document?")) return;
    try {
      await api.deleteDocument(documentId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete document.");
    }
  }

  if (!collection || documents === null) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        Loading...
      </div>
    );
  }

  return (
    <div>
      <Link to="/collections" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />
        Back to collections
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">{collection.name}</h1>
      {collection.description && <p className="mt-1 text-sm text-muted-foreground">{collection.description}</p>}
      <p className="mt-1 text-xs text-muted-foreground">
        chunk_size={collection.chunk_size} · chunk_overlap={collection.chunk_overlap} · {collection.embedding_model}
      </p>

      {error && (
        <Alert variant="destructive" className="mt-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card
        className="mt-6 cursor-pointer border-dashed"
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
        }}
      >
        <CardContent className={`flex flex-col items-center justify-center gap-2 py-10 text-center ${isDragging ? "bg-accent" : ""}`}>
          <UploadCloud className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium">
            {isUploading ? "Uploading..." : "Drag & drop files here, or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground">PDF, DOCX, Markdown, or HTML</p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept=".pdf,.docx,.md,.markdown,.html,.htm"
            onChange={(e) => e.target.files && uploadFiles(e.target.files)}
          />
        </CardContent>
      </Card>

      <div className="mt-4 flex gap-2" onClick={(e) => e.stopPropagation()}>
        <Input
          placeholder="https://example.com/article"
          value={urlValue}
          onChange={(e) => setUrlValue(e.target.value)}
        />
        <Button variant="secondary" onClick={handleUrlSubmit} disabled={isUploading || !urlValue.trim()}>
          Fetch URL
        </Button>
      </div>

      <div className="mt-8">
        <h2 className="mb-3 text-lg font-medium">Documents</h2>
        {documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
        ) : (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Chunks</TableHead>
                  <TableHead>Uploaded</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell className="max-w-xs">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="truncate">{doc.filename}</span>
                      </div>
                      {doc.status === "FAILED" && doc.error_message && (
                        <p className="mt-1 truncate text-xs text-destructive">{doc.error_message}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-1">
                        <Badge variant={STATUS_VARIANT[doc.status] ?? "default"}>{doc.status}</Badge>
                        {ACTIVE_STATUSES.has(doc.status) && <Progress value={statusToPct(doc.status)} className="w-24" />}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatBytes(doc.file_size)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{doc.chunk_count}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDateTime(doc.created_at)}</TableCell>
                    <TableCell>
                      <button
                        onClick={() => handleDelete(doc.id)}
                        className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        aria-label={`Delete ${doc.filename}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>
    </div>
  );
}

function statusToPct(status: string): number {
  switch (status) {
    case "QUEUED":
      return 5;
    case "PARSING":
      return 25;
    case "CHUNKING":
      return 50;
    case "EMBEDDING":
      return 75;
    default:
      return 100;
  }
}
