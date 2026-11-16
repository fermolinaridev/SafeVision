export type Equipment = "helmet" | "vest";
export type Status = "open" | "reviewed" | "dismissed";
export type Bucket = "day" | "week" | "month";
export type Camera = { id: string; name: string; location: string; last_seen: string | null };
export type Occurrence = {
  id: string; camera_id: string; camera_name: string; video_id: string | null;
  equipment: Equipment; track_id: number; confidence: number; duration: number;
  status: Status; evidence_url: string | null; occurred_at: string;
  frame_seconds: number; reviewed_at: string | null;
};
export type EventPage = { items: Occurrence[]; total: number };
export type Summary = {
  total: number; previous_total: number; helmet: number; vest: number; open: number;
  cameras_total: number; cameras_active: number; timezone: string;
  timeline: { date: string; helmet: number; vest: number }[];
  cameras: { id: string; name: string; count: number }[];
  hours: { hour: number; count: number }[];
};
export type Session = {
  authenticated: boolean; demo: boolean; timezone: string;
  image_mb: number; video_mb: number; max_video_seconds: number;
};
export type Health = {
  services: Record<string, boolean | null>; model_configured: boolean; model_loaded: boolean;
  analyses: number; average_inference_ms: number | null; device: string;
};
type Assessment = { state: "present" | "missing" | "unknown"; confidence: number | null };
export type Analysis = {
  width: number; height: number; inference_ms: number;
  detections: { label: string; confidence: number; box: [number, number, number, number]; track_id: number | null }[];
  people: { detection_index: number; track_id: number | null; helmet: Assessment; vest: Assessment }[];
};
export type Job = {
  id: string; filename: string; camera_id: string; created_at: string; recorded_at: string; progress: number;
  status: "pending" | "running" | "completed" | "failed"; error: string | null;
  processed_frames: number; processing_seconds: number | null;
};
export type Filters = {
  start: string; end: string; camera_id: string; equipment: Equipment | ""; status: Status | "";
};

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login") window.dispatchEvent(new Event("session-expired"));
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? "O serviço está indisponível. Tente novamente.");
  }
  return response.status === 204 ? undefined as T : response.json();
}

export const json = (method: string, body: unknown): RequestInit => ({
  method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" },
});

export function socket(path: string) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return new WebSocket(`${protocol}//${location.host}${path}`);
}

export function filterQuery(filters: Filters, extra?: Record<string, string>) {
  return new URLSearchParams(Object.entries({ ...filters, ...extra }).filter(([, value]) => value !== "")).toString();
}

export const equipmentName = { helmet: "Capacete", vest: "Colete" };
export const statusName = { open: "Pendente", reviewed: "Revisada", dismissed: "Descartada" };
export const jobStatus = { pending: "Na fila", running: "Processando", completed: "Concluído", failed: "Falhou" };
export const detectionName: Record<string, string> = {
  person: "Pessoa", helmet: "Capacete", vest: "Colete", no_helmet: "Sem capacete", no_vest: "Sem colete",
};
export const number = (value: number) => new Intl.NumberFormat("pt-BR").format(value);
export const percent = (value: number) => new Intl.NumberFormat("pt-BR", {
  style: "percent", maximumFractionDigits: 0,
}).format(value);
export function dateTime(value: string, timezone: string, onlyTime = false) {
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: timezone,
    ...(onlyTime ? {} : { day: "2-digit", month: "short", year: "numeric" }),
    hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}
export function localDay(zone: string, offset = 0) {
  const current = new Intl.DateTimeFormat("en-CA", { timeZone: zone, dateStyle: "short" }).format(new Date());
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const part = (key: string) => parts.find((item) => item.type === key)?.value ?? "";
  const iso = `${part("year")}-${part("month")}-${part("day")}`;
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso : current;
  const day = new Date(normalized + "T12:00:00Z");
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toISOString().slice(0, 10);
}
export function cameraActive(camera: Camera) {
  return camera.last_seen !== null && Date.now() - new Date(camera.last_seen).getTime() < 120_000;
}
