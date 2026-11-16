import { useEffect, useRef, useState, type FormEvent } from "react";
import { Camera as CameraIcon, FileVideo, HardHat, Image, ScanLine, Shirt, UploadCloud, Video, X } from "lucide-react";
import {
  api, dateTime, detectionName, jobStatus, number, percent, socket,
  type Analysis, type Camera, type Job, type Session,
} from "./api";
import { Empty, ErrorNotice } from "./components";

type InputMode = "image" | "video" | "webcam";
const samples = [
  { name: "Doca de carga", path: "/examples/doca.jpg" },
  { name: "Estrutura", path: "/examples/estrutura.jpg" },
  { name: "Pátio externo", path: "/examples/patio.jpg" },
];
const assessmentLabel = { present: "Presente", missing: "Ausente", unknown: "Inconclusivo" };

function Boxes({ analysis }: { analysis: Analysis }) {
  return <div className="overlays">
    {analysis.detections.map(({ label, confidence, box, track_id }, index) => {
      const [x1, y1, x2, y2] = box;
      return <div key={index} className={`detection-box ${label.startsWith("no_") ? "absent" : label === "person" ? "person" : ""}`}
        style={{
          left: `${x1 * 100 / analysis.width}%`, top: `${y1 * 100 / analysis.height}%`,
          width: `${(x2 - x1) * 100 / analysis.width}%`, height: `${(y2 - y1) * 100 / analysis.height}%`,
        }}>
        <span>{detectionName[label] ?? label} {percent(confidence)}{track_id === null ? "" : ` #${track_id}`}</span>
      </div>;
    })}
  </div>;
}

function Annotated({ source, analysis }: { source: string; analysis: Analysis | null }) {
  return <div className="annotated"><img src={source} alt="Imagem de análise de EPIs" />
    {analysis && <Boxes analysis={analysis} />}
  </div>;
}

function Findings({ analysis }: { analysis: Analysis }) {
  return <section className="panel work-card">
    <div className="panel-heading"><div><h2>Leitura por pessoa</h2>
      <p>{analysis.detections.length} detecções · {number(Math.round(analysis.inference_ms))} ms</p></div></div>
    {analysis.people.length ? <div className="findings">
      {analysis.people.map((person, index) => <article key={person.detection_index}>
        <strong>Pessoa #{person.track_id ?? index + 1}</strong>
        {(["helmet", "vest"] as const).map((equipment) => <span key={equipment}>
          {equipment === "helmet" ? <HardHat size={16} /> : <Shirt size={16} />}
          {equipment === "helmet" ? "Capacete" : "Colete"}
          <b className={person[equipment].state}>{assessmentLabel[person[equipment].state]}</b>
        </span>)}
      </article>)}
    </div> : <Empty title="Nenhuma pessoa detectada" />}
  </section>;
}

function MediaInput({ mode, session, cameras, initialCamera }: {
  mode: "image" | "video"; session: Session; cameras: Camera[]; initialCamera: string;
}) {
  const [file, setFile] = useState<File>();
  const [sample, setSample] = useState<string>();
  const [preview, setPreview] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [camera, setCamera] = useState(initialCamera || "");
  const [recorded, setRecorded] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [message, setMessage] = useState("");
  const [jobsError, setJobsError] = useState("");
  const [busy, setBusy] = useState(false);
  const request = useRef(new AbortController());
  const input = useRef<HTMLInputElement>(null);
  const video = mode === "video";
  const limit = video ? session.video_mb : session.image_mb;

  useEffect(() => {
    if (!file) { setPreview(sample ?? ""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file, sample]);

  useEffect(() => () => request.current.abort(), []);

  useEffect(() => {
    if (!video || session.demo) return;
    const controller = new AbortController();
    const refresh = () => api<Job[]>("/videos", { signal: controller.signal })
      .then((data) => { setJobs(data); setJobsError(""); })
      .catch((error) => { if (!controller.signal.aborted) setJobsError(error.message); });
    void refresh();
    const interval = window.setInterval(refresh, 2200);
    return () => { controller.abort(); clearInterval(interval); };
  }, [video, session.demo]);

  const choose = (newFile?: File, newSample?: string) => {
    setMessage(""); setAnalysis(null);
    if (newFile && newFile.size > limit * 1024 * 1024) {
      setMessage(`Use um arquivo de até ${limit} MB.`); return;
    }
    setFile(newFile); setSample(newSample);
    if (input.current) input.current.value = "";
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || (!file && !sample)) return;
    const controller = new AbortController();
    request.current = controller;
    setMessage(""); setBusy(true);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      else if (sample) {
        const response = await fetch(sample, { signal: controller.signal });
        if (!response.ok) throw new Error("O exemplo está indisponível.");
        form.append("file", await response.blob(), sample.split("/").at(-1));
      }
      if (video) {
        form.append("camera_id", camera || cameras[0]?.id || "cam-01");
        if (recorded) form.append("recorded_at", new Date(recorded).toISOString());
        const job = await api<Job>("/videos", { method: "POST", body: form, signal: controller.signal });
        setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
        choose();
      } else {
        setAnalysis(await api<Analysis>("/detect", { method: "POST", body: form, signal: controller.signal }));
      }
    } catch (error) {
      if (!controller.signal.aborted) setMessage((error as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function retry(id: string) {
    setJobsError("");
    try {
      const job = await api<Job>(`/videos/${id}/retry`, { method: "POST" });
      setJobs((current) => current.map((item) => item.id === id ? job : item));
    } catch (error) { setJobsError((error as Error).message); }
  }

  return <>
    <form className="panel work-card" onSubmit={submit}>
      <div className="panel-heading"><div><h2>{video ? "Enviar vídeo" : "Enviar imagem"}</h2>
        <p>{video ? `MP4, MOV ou WebM · até ${limit} MB e ${session.max_video_seconds} s` : `JPG, PNG ou WebP · até ${limit} MB`}</p></div></div>
      {video && session.demo
        ? <div className="sample-video"><video controls preload="metadata" src="/examples/obra-video.mp4" />
          <p>O processamento de vídeos está disponível na instalação com fila e armazenamento.</p></div>
        : <>
          <input className="sr-only" tabIndex={-1} ref={input} aria-label={video ? "Arquivo de vídeo" : "Arquivo de imagem"} type="file"
            accept={video ? "video/mp4,video/webm,video/quicktime,.mov" : "image/jpeg,image/png,image/webp"}
            onChange={(event) => { const selected = event.target.files?.[0]; if (selected) choose(selected); }} />
          {preview ? <div className="upload-preview">
            <button type="button" className="icon-button clear-preview" aria-label="Remover arquivo" disabled={busy} onClick={() => choose()}><X size={18} /></button>
            {video ? <video controls preload="metadata" src={preview} /> : <Annotated source={preview} analysis={analysis} />}
          </div> : <button type="button" className="drop-zone" onClick={() => input.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => { event.preventDefault(); if (event.dataTransfer.files[0]) choose(event.dataTransfer.files[0]); }}>
            <span className="metric-icon mint"><UploadCloud size={24} /></span><strong>Selecionar {video ? "vídeo" : "imagem"}</strong>
            <span>ou arraste um arquivo para cá</span>
          </button>}
          {video && <div className="form-grid">
            <label>Câmera<select value={camera || cameras[0]?.id || ""} onChange={(event) => setCamera(event.target.value)}>
              {cameras.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select></label>
            <label>Data de gravação <small>(opcional, horário deste dispositivo)</small><input type="datetime-local" value={recorded}
              onChange={(event) => setRecorded(event.target.value)} /></label>
          </div>}
          {message && <ErrorNotice message={message} />}
          <div className="upload-actions">
            {video ? <button type="button" className="text-button" onClick={() => choose(undefined, "/examples/teste-ocorrencia.mp4")} disabled={busy}><FileVideo size={16} /> Usar vídeo de exemplo</button>
              : <div className="sample-actions">{samples.map((item) => <button key={item.path} type="button" className="sample-button"
                onClick={() => choose(undefined, item.path)} aria-pressed={sample === item.path} disabled={busy}>
                <img src={item.path} alt="" />{item.name}
              </button>)}</div>}
            <button className="button primary" disabled={busy || (!file && !sample) || (video && !cameras.length)}>
              <ScanLine size={18} />{busy ? "Enviando…" : video ? "Processar vídeo" : "Analisar imagem"}
            </button>
          </div>
        </>}
    </form>
    {analysis && <Findings analysis={analysis} />}
    {video && !session.demo && <section className="panel work-card">
      <div className="panel-heading"><div><h2>Processamentos recentes</h2><p>Status da fila de vídeos</p></div></div>
      {jobsError && <ErrorNotice message={jobsError} />}
      {jobs.length ? <div className="jobs">{jobs.map((job) => <article key={job.id}>
        <FileVideo size={20} /><div><strong>{job.filename}</strong>
          <small>{dateTime(job.created_at, session.timezone)} · {job.processed_frames} frames analisados</small>
          {job.error && <small className="job-error">{job.error}</small>}
        </div><div className="job-progress"><span className={job.status === "failed" ? "job-error" : ""}>{jobStatus[job.status]}</span>
          <progress value={job.progress} max={100} aria-label={`Progresso de ${job.filename}`} /></div>
        {job.status === "failed" && <button type="button" className="button secondary-button" onClick={() => void retry(job.id)}>Repetir</button>}
      </article>)}</div> : <Empty title="Nenhum vídeo enviado" />}
    </section>}
  </>;
}

function Webcam({ session, cameras, initialCamera }: { session: Session; cameras: Camera[]; initialCamera: string }) {
  const [active, setActive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [preview, setPreview] = useState("");
  const [camera, setCamera] = useState(initialCamera);
  const [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const running = useRef<AbortController | null>(null);

  function stop() {
    running.current?.abort(); running.current = null;
    setActive(false); setStarting(false);
  }

  useEffect(() => () => running.current?.abort(), []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function start() {
    if (running.current) return;
    const controller = new AbortController();
    const { signal } = controller;
    running.current = controller;
    setStarting(true); setError(""); setPreview(""); setAnalysis(null);
    let ws: WebSocket | undefined;
    let timer: number | undefined;
    let media: MediaStream | undefined;
    const selectedCamera = camera || cameras[0]?.id;
    const source = video.current;
    let pending: Blob | undefined;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    function schedule() { if (!signal.aborted) timer = window.setTimeout(() => void frame(), session.demo ? 750 : 255); }
    function display(blob: Blob, result: Analysis) {
      if (signal.aborted) return;
      setPreview(URL.createObjectURL(blob)); setAnalysis(result);
    }
    async function frame() {
      if (signal.aborted || !source || !ctx || !source.videoWidth) { schedule(); return; }
      const scale = Math.min(1, 720 / Math.max(source.videoWidth, source.videoHeight));
      canvas.width = Math.round(source.videoWidth * scale);
      canvas.height = Math.round(source.videoHeight * scale);
      ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.78));
      if (signal.aborted) return;
      if (!blob) { schedule(); return; }
      if (!session.demo) {
        if (ws?.readyState === WebSocket.OPEN) { pending = blob; ws.send(blob); }
        return;
      }
      try {
        const form = new FormData(); form.append("file", blob, "webcam.jpg");
        display(blob, await api<Analysis>("/detect", { method: "POST", body: form, signal }));
        if (!signal.aborted) setError("");
      } catch (cause) {
        if (!signal.aborted) setError((cause as Error).message);
      }
      schedule();
    }
    signal.addEventListener("abort", () => {
      clearTimeout(timer); ws?.close(); media?.getTracks().forEach((track) => track.stop());
      if (source) source.srcObject = null;
    }, { once: true });

    try {
      if (!navigator.mediaDevices?.getUserMedia || !source || !ctx) throw new Error("A webcam requer HTTPS ou localhost.");
      media = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 720 } }, audio: false });
      if (signal.aborted) { media.getTracks().forEach((track) => track.stop()); return; }
      source.srcObject = media;
      await source.play();
      if (signal.aborted) return;
      setActive(true); setStarting(false);
      if (session.demo) { schedule(); return; }
      if (!selectedCamera) throw new Error("Cadastre uma câmera antes de iniciar.");
      ws = socket(`/cameras/${selectedCamera}/live`);
      ws.onopen = schedule;
      ws.onmessage = (event) => {
        if (signal.aborted) return;
        const data = JSON.parse(event.data);
        if (data.type === "analysis" && pending) { display(pending, data.analysis); setError(""); }
        if (data.type === "error") setError(data.message);
        schedule();
      };
      ws.onclose = () => { if (!signal.aborted) { stop(); setError("A conexão de monitoramento foi encerrada."); } };
    } catch (cause) {
      if (!signal.aborted) {
        stop();
        setError(cause instanceof DOMException ? "Não foi possível acessar a webcam. Confira as permissões do navegador." : (cause as Error).message);
      }
    }
  }

  return <>
    <section className="panel work-card">
      <div className="panel-heading"><div><h2>Webcam ao vivo</h2>
        <p>{session.demo ? "Análise de frames ao vivo em modo demonstração." : "Detecção e rastreamento de pessoas na câmera selecionada."}</p></div>
        {active && <button className="button secondary-button" onClick={stop}>Parar webcam</button>}
      </div>
      <video ref={video} className="camera-source" muted playsInline />
      {active && preview ? <div className="upload-preview"><Annotated source={preview} analysis={analysis} /></div>
        : <div className="drop-zone webcam-placeholder"><span className="metric-icon mint"><Video size={25} /></span>
          <strong>{active ? "Aguardando a primeira análise…" : "Use a câmera deste dispositivo"}</strong>
        </div>}
      {!session.demo && <label className="camera-select">Câmera<select disabled={active || starting} value={camera || cameras[0]?.id || ""}
        onChange={(event) => setCamera(event.target.value)}>
        {cameras.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      {error && <ErrorNotice message={error} />}
      {!active && <div className="upload-actions"><button className="button primary" onClick={() => void start()}
        disabled={starting || (!session.demo && !cameras.length)}><CameraIcon size={18} />{starting ? "Conectando…" : "Iniciar webcam"}</button></div>}
    </section>
    {active && analysis && <Findings analysis={analysis} />}
  </>;
}

export function Media({ session, cameras, initialCamera, initialMode }: {
  session: Session; cameras: Camera[]; initialCamera: string; initialMode: InputMode;
}) {
  const [mode, setMode] = useState<InputMode>(initialMode);
  return <div className="work-stack">
    <div className="media-tabs" aria-label="Tipo de análise">
      {([["image", "Imagem", Image], ["video", "Vídeo", FileVideo], ["webcam", "Webcam", CameraIcon]] as const).map(([id, label, Icon]) =>
        <button key={id} className={mode === id ? "selected" : ""} aria-pressed={mode === id} onClick={() => setMode(id)}><Icon size={18} />{label}</button>)}
    </div>
    {mode === "webcam" ? <Webcam session={session} cameras={cameras} initialCamera={initialCamera} />
      : <MediaInput key={mode} mode={mode} session={session} cameras={cameras} initialCamera={initialCamera} />}
  </div>;
}
