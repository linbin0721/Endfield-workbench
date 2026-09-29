import type { components } from "./generated/api";
import type { BalloonPuzzle } from "./puzzle";

export type Capability = components["schemas"]["PuzzleCapability"];
export type Task = components["schemas"]["TaskView"];
export type BalloonTask = components["schemas"]["BalloonSolveTaskView"];
export type RecognitionTask = components["schemas"]["BalloonRecognitionTaskView"];
export type RecognitionResult = components["schemas"]["BalloonRecognitionResult"];
export type CatalogEntry = components["schemas"]["CatalogEntry"];
export type CatalogCandidate = components["schemas"]["CatalogCandidate"];
export type CatalogMatch = components["schemas"]["CatalogMatch"];
export type CircuitPuzzle = components["schemas"]["CircuitPuzzle"];
export type CircuitRecognitionResult = components["schemas"]["CircuitRecognitionResult"];
export type CircuitSolveResult = components["schemas"]["CircuitSolveResult"];
export type CircuitRecognitionTaskView = components["schemas"]["CircuitRecognitionTaskView"];
export type CircuitSolveTaskView = components["schemas"]["CircuitSolveTaskView"];
export type CircuitCatalogCandidate = components["schemas"]["CircuitCatalogCandidate"];
export type CircuitCatalogEntry = components["schemas"]["CircuitCatalogEntry"];
export type CircuitCatalogMatch = components["schemas"]["CircuitCatalogMatch"];

const configured = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE = configured || (import.meta.env.DEV ? "http://localhost:8000" : "");

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE) throw new ApiError(0, "NO_API_URL", "解题服务尚未配置，请联系站点维护者。");
  let response: Response;
  try {
    response = await fetch(`${API_BASE.replace(/\/$/, "")}${path}`, init);
  } catch {
    if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    throw new ApiError(0, "NETWORK_ERROR", "无法连接解题服务。请检查网络或稍后重试。");
  }
  let body: unknown;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) {
    const detail = body && typeof body === "object" && "error" in body ? (body as { error?: { code?: string; message?: string } }).error : undefined;
    throw new ApiError(response.status, detail?.code || "HTTP_ERROR", detail?.message || `服务返回 ${response.status}。`);
  }
  return body as T;
}

export const getCapabilities = (signal?: AbortSignal) => request<Capability[]>("/api/v1/puzzles", { signal });
export const submitBalloon = (puzzle: BalloonPuzzle, signal?: AbortSignal) => request<BalloonTask>(
  "/api/v1/puzzles/balloon/solve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(puzzle), signal },
);
export const submitRecognition = (image: Blob, filename: string) => {
  const form = new FormData();
  form.append("image", image, filename);
  return request<RecognitionTask>("/api/v1/puzzles/balloon/recognize", { method: "POST", body: form });
};
export const getTask = (id: string, signal?: AbortSignal) => request<Task>(`/api/v1/tasks/${encodeURIComponent(id)}`, { signal });
export const cancelTask = (id: string, signal?: AbortSignal) => request<Task>(`/api/v1/tasks/${encodeURIComponent(id)}`, { method: "DELETE", signal });
export const getCatalogEntry = (code: string, signal?: AbortSignal) => request<CatalogEntry>(
  `/api/v1/puzzles/balloon/catalog/${encodeURIComponent(code.trim())}`, { signal },
);
export const submitCircuitRecognition = (image: Blob, filename: string) => {
  const form = new FormData();
  form.append("image", image, filename);
  return request<CircuitRecognitionTaskView>("/api/v1/puzzles/circuit/recognize", { method: "POST", body: form });
};
export const submitCircuit = (puzzle: CircuitPuzzle, signal?: AbortSignal) => request<CircuitSolveTaskView>(
  "/api/v1/puzzles/circuit/solve",
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(puzzle), signal },
);
export const getCircuitCatalogEntry = (code: string, signal?: AbortSignal) => request<CircuitCatalogEntry>(
  `/api/v1/puzzles/circuit/catalog/${encodeURIComponent(code.trim())}`, { signal },
);
