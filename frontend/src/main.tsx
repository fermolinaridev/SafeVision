import { lazy, StrictMode, Suspense, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, ArrowRight, Bell, CalendarDays, Camera as CameraIcon, ChevronDown, ChevronLeft, ChevronRight,
  CircleHelp, Clapperboard, ClipboardList, Clock3, ExternalLink, Images, LayoutGrid, LogOut, Menu, Plus,
  Radio, Settings as SettingsIcon, ShieldCheck, Video, X,
} from "lucide-react";
import {
  api, cameraActive, dateTime, filterQuery, json, localDay, number, percent, socket,
  type Bucket, type Camera, type EventPage, type Filters, type Health, type Occurrence, type Session,
  type Status, type Summary,
} from "./api";
import { Brand, DateFilters, Empty, EquipmentTag, ErrorNotice, EventTable, Modal, StatusTag } from "./components";
import { Media } from "./media";
import "./styles.css";

const Metrics = lazy(() => import("./dashboard").then(({ Metrics }) => ({ default: Metrics })));
const MainCharts = lazy(() => import("./dashboard").then(({ MainCharts }) => ({ default: MainCharts })));
const SecondaryCharts = lazy(() => import("./dashboard").then(({ SecondaryCharts }) => ({ default: SecondaryCharts })));

const nav = [
  { label: "MONITORAMENTO", items: [
    { id: "overview", label: "Visão geral", icon: LayoutGrid },
    { id: "events", label: "Ocorrências", icon: ClipboardList },
    { id: "evidence", label: "Evidências", icon: Images },
    { id: "cameras", label: "Câmeras", icon: CameraIcon },
  ] },
  { label: "OPERAÇÃO", items: [
    { id: "media", label: "Análise de mídia", icon: Clapperboard },
    { id: "settings", label: "Configurações", icon: SettingsIcon },
  ] },
] as const;
type Page = typeof nav[number]["items"][number]["id"];
const pages = nav.flatMap((group) => [...group.items]);
const pageCopy: Record<Page, { title: string; subtitle: string }> = {
  overview: { title: "Visão geral", subtitle: "Acompanhe o uso de EPIs e as ocorrências em suas áreas monitoradas." },
  events: { title: "Ocorrências", subtitle: "Consulte e acompanhe as violações detectadas." },
  evidence: { title: "Evidências", subtitle: "Explore os frames capturados no momento de cada ocorrência." },
  cameras: { title: "Câmeras", subtitle: "Acompanhe a atividade e as fontes de monitoramento cadastradas." },
  media: { title: "Análise de mídia", subtitle: "Identifique pessoas, capacetes e coletes em imagens, vídeos ou na webcam." },
  settings: { title: "Configurações", subtitle: "Consulte os limites de análise e a disponibilidade dos serviços." },
};

function pageFromHash(): Page {
  const hash = window.location.hash.slice(1);
  return pages.find((page) => page.id === hash)?.id || "overview";
}

function useData<T>(path: string | null, refresh = 0) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    api<T>(path, { signal: controller.signal })
      .then((result) => { setData(result); setError(""); })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [path, refresh]);
  return { data, error };
}

function Layout({ session, page, go, children, live, pending, logout }: {
  session: Session; page: Page; go: (page: Page) => void; children: ReactNode;
  live: boolean; pending: () => void; logout: () => Promise<void>;
}) {
  const [mobile, setMobile] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  return <div className="layout">
    {mobile && <button className="mobile-scrim" onClick={() => setMobile(false)} aria-label="Fechar menu" />}
    <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
      <a href="#overview" className="brand-link" onClick={() => { go("overview"); setMobile(false); }}><Brand /></a>
      <button className="sidebar-close icon-button" onClick={() => setMobile(false)} aria-label="Fechar menu"><X size={22} /></button>
      <nav aria-label="Navegação principal">{nav.map((group) => <div className="nav-group" key={group.label}>
        <p>{group.label}</p>
        {group.items.map(({ id, label, icon: Icon }) => <a href={`#${id}`} key={id} aria-current={page === id ? "page" : undefined}
          onClick={(event) => { event.preventDefault(); go(id); setMobile(false); }}>
          <Icon size={18} strokeWidth={1.75} />{label}
        </a>)}
      </div>)}</nav>
      <div className="sidebar-footer">
        <div className="sidebar-status"><span className="indicator"><i /></span><div>
          <strong>{session.demo ? "Modo demonstração" : live ? "Eventos conectados" : "Eventos desconectados"}</strong>
          <small>{session.demo ? "Dados ilustrativos" : "Monitoramento de EPIs"}</small>
        </div></div>
        <a href="/docs" target="_blank" rel="noreferrer"><CircleHelp size={17} /> Documentação <ExternalLink size={13} /></a>
      </div>
    </aside>
    <div className="shell">
      <header className="topbar">
        <button className="icon-button mobile-toggle" aria-label="Abrir menu" onClick={() => setMobile(true)}><Menu size={22} /></button>
        <div className="breadcrumb"><span>{nav[1].items.some((item) => item.id === page) ? "Operação" : "Monitoramento"}</span><ChevronRight size={14} /><strong>{pageCopy[page].title}</strong></div>
        <div className="header-actions">
          <span className={`live-badge ${live ? "" : "offline"}`}><i />{session.demo ? "Demonstração" : live ? "Ao vivo" : "Reconectando"}</span>
          <button className="icon-button bell" onClick={pending} aria-label="Ver ocorrências pendentes"><Bell size={19} /></button>
          <div className="account">
            <button className="account-button" aria-expanded={userMenu} aria-label="Menu da conta" onClick={() => setUserMenu(!userMenu)}>
              <span className="avatar">{session.demo ? "SV" : "AD"}</span><span>{session.demo ? "Visitante" : "Admin"}</span><ChevronDown size={14} />
            </button>
            {userMenu && <div className="account-menu">
              <button onClick={() => { go("settings"); setUserMenu(false); }}><SettingsIcon size={16} /> Configurações</button>
              {!session.demo && <button onClick={() => { setUserMenu(false); void logout(); }}><LogOut size={16} /> Sair</button>}
            </div>}
          </div>
        </div>
      </header>
      <main>{children}</main>
      <footer className="footer"><a href="/creditos" target="_blank" rel="noreferrer">Créditos da mídia</a>
        <span>{session.timezone === "America/Sao_Paulo" ? "Horário de São Paulo" : session.timezone.replaceAll("_", " ")}</span></footer>
    </div>
  </div>;
}

function Login({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function login(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try { await api("/auth/login", json("POST", { password })); onLogin(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="login-shell"><form className="login-panel" onSubmit={login}>
    <Brand /><h1>Acessar o SafeVision</h1>
    <label>Senha de administrador<input type="password" value={password} autoComplete="current-password" required
      onChange={(event) => setPassword(event.target.value)} autoFocus /></label>
    {error && <ErrorNotice message={error} />}
    <button type="submit" className="button primary" disabled={busy}>{busy ? "Entrando…" : "Entrar"}<ArrowRight size={18} /></button>
  </form></div>;
}

function EventDetails({ item, session, close, refresh }: {
  item: Occurrence; session: Session; close: () => void; refresh: () => void;
}) {
  const [event, setEvent] = useState(item);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmDeletion, setConfirmDeletion] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api<Occurrence>(`/events/${item.id}`, { signal: controller.signal }).then(setEvent)
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [item.id]);

  async function update(status: Status) {
    setBusy(true); setError("");
    try { setEvent(await api<Occurrence>(`/events/${item.id}`, json("PATCH", { status }))); refresh(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function removeEvidence() {
    setBusy(true); setError("");
    try {
      await api(`/events/${item.id}/evidence`, { method: "DELETE" });
      setEvent((current) => ({ ...current, evidence_url: null })); setConfirmDeletion(false); refresh();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <Modal title="Detalhes da ocorrência" onClose={close}>
    {session.demo && <div className="demo-note"><Images size={16} /> Evidência ilustrativa da demonstração</div>}
    {event.evidence_url ? <img className="detail-image" src={event.evidence_url} alt="Frame associado à ocorrência" /> : <Empty title="Evidência indisponível" />}
    <div className="detail-tags"><EquipmentTag equipment={event.equipment} /><StatusTag status={event.status} /></div>
    <dl className="detail-grid">
      <div><dt>Câmera</dt><dd>{event.camera_name}</dd></div>
      <div><dt>Data e hora</dt><dd>{dateTime(event.occurred_at, session.timezone)}</dd></div>
      <div><dt>Pessoa rastreada</dt><dd>#{event.track_id}</dd></div>
      <div><dt>Confiança da detecção</dt><dd>{percent(event.confidence)}</dd></div>
      <div><dt>Duração observada</dt><dd>{number(Number(event.duration.toFixed(2)))} s</dd></div>
      <div><dt>{event.video_id ? "Posição no vídeo" : "Posição na sessão"}</dt><dd>{number(Number(event.frame_seconds.toFixed(2)))} s</dd></div>
    </dl>
    {error && <ErrorNotice message={error} />}
    {confirmDeletion && <div className="delete-confirm" role="alert">
      <p>Excluir permanentemente o frame associado a esta ocorrência?</p>
      <button className="button secondary-button" disabled={busy} onClick={() => setConfirmDeletion(false)}>Cancelar</button>
      <button className="button danger" disabled={busy} onClick={() => void removeEvidence()}>Excluir frame</button>
    </div>}
    {!session.demo && <div className="modal-actions">
      {event.evidence_url && !confirmDeletion && <button className="text-button remove-evidence" disabled={busy} onClick={() => setConfirmDeletion(true)}>Excluir evidência</button>}
      {event.status !== "open" && <button className="button secondary-button" disabled={busy} onClick={() => void update("open")}>Reabrir</button>}
      {event.status !== "dismissed" && <button className="button secondary-button" disabled={busy} onClick={() => void update("dismissed")}>Descartar</button>}
      {event.status !== "reviewed" && <button className="button primary" disabled={busy} onClick={() => void update("reviewed")}><ShieldCheck size={17} /> Marcar revisada</button>}
    </div>}
  </Modal>;
}

function Gallery({ items, timezone, onSelect }: { items: Occurrence[]; timezone: string; onSelect: (event: Occurrence) => void }) {
  if (!items.length) return <div className="panel"><Empty title="Nenhuma ocorrência no período" /></div>;
  return <div className="gallery">{items.map((event) => <button className="panel gallery-card" key={event.id} onClick={() => onSelect(event)}>
    {event.evidence_url ? <img src={event.evidence_url} loading="lazy" alt="" /> : <div className="gallery-placeholder"><Images size={26} />Evidência indisponível</div>}
    <div><EquipmentTag equipment={event.equipment} /><h2>{event.camera_name}</h2><p>{dateTime(event.occurred_at, timezone)}</p></div>
  </button>)}</div>;
}

function CameraPage({ cameras, session, useCamera, refresh }: {
  cameras: Camera[]; session: Session; useCamera: (id: string) => void; refresh: () => void;
}) {
  const [modal, setModal] = useState(false);
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function add(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try { await api("/cameras", json("POST", { name, location })); setModal(false); setName(""); setLocation(""); refresh(); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  return <>
    {!session.demo && <div className="inline-end"><button className="button primary" onClick={() => setModal(true)}><Plus size={19} /> Cadastrar câmera</button></div>}
    <div className="camera-grid">{cameras.map((camera) => <article className="panel work-card camera-card" key={camera.id}>
      <div className="panel-heading"><span className="metric-icon mint"><CameraIcon size={22} /></span>
        <span className={`live-badge ${cameraActive(camera) ? "" : "offline"}`}><i />{cameraActive(camera) ? "Ativa" : "Sem sinal recente"}</span></div>
      <h2>{camera.name}</h2><p>{camera.location}</p>
      <small><Clock3 size={14} />{camera.last_seen ? dateTime(camera.last_seen, session.timezone) : "Sem atividade registrada"}</small>
      <button className="button secondary-button" onClick={() => useCamera(camera.id)}><Video size={17} /> Usar webcam</button>
    </article>)}</div>
    {!cameras.length && <div className="panel"><Empty title="Nenhuma câmera cadastrada" /></div>}
    {modal && <Modal title="Cadastrar câmera" onClose={() => setModal(false)}><form className="dialog-form" onSubmit={add}>
      <label>Nome da câmera<input required minLength={2} maxLength={100} value={name} onChange={(event) => setName(event.target.value)} autoFocus /></label>
      <label>Local<input required minLength={2} maxLength={120} value={location} onChange={(event) => setLocation(event.target.value)} /></label>
      {error && <ErrorNotice message={error} />}
      <button className="button primary" disabled={busy}>Cadastrar</button>
    </form></Modal>}
  </>;
}

function SettingsPage({ session }: { session: Session }) {
  const [refresh, setRefresh] = useState(0);
  const { data, error } = useData<Health>("/health", refresh);
  const names: Record<string, string> = { api: "API", database: "PostgreSQL", queue: "Redis", storage: "Armazenamento S3" };
  return <div className="work-stack">
    <section className="panel work-card">
      <div className="panel-heading"><div><h2>Disponibilidade</h2><p>Conectividade dos serviços da aplicação</p></div>
        <button className="button secondary-button" onClick={() => setRefresh(refresh + 1)}><Activity size={16} /> Atualizar</button></div>
      {error && <ErrorNotice message={error} />}
      <div className="service-grid">{data && Object.entries(data.services).map(([name, service]) =>
        <div key={name}><strong>{names[name]}</strong><span className={`live-badge ${service ? "" : "offline"}`}><i />
          {service === null ? "Fora da demonstração" : service ? "Disponível" : "Indisponível"}
        </span></div>)}</div>
    </section>
    <section className="panel work-card">
      <div className="panel-heading"><div><h2>Inferência de imagens</h2><p>Indicadores do processo da API</p></div></div>
      {data && <dl className="detail-grid">
        <div><dt>Checkpoint</dt><dd>{data.model_configured ? data.model_loaded ? "Carregado" : "Configurado" : "Indisponível"}</dd></div>
        <div><dt>Dispositivo</dt><dd>{data.device.toUpperCase()}</dd></div>
        <div><dt>Análises concluídas</dt><dd>{number(data.analyses)}</dd></div>
        <div><dt>Tempo médio das últimas análises</dt><dd>{data.average_inference_ms === null ? "—" : `${number(data.average_inference_ms)} ms`}</dd></div>
        <div><dt>Tamanho máximo da imagem</dt><dd>{session.image_mb} MB</dd></div>
        {!session.demo && <div><dt>Limites de vídeo</dt><dd>{session.video_mb} MB · {session.max_video_seconds} s</dd></div>}
      </dl>}
    </section>
  </div>;
}

function Workspace({ session, logout }: { session: Session; logout: () => Promise<void> }) {
  const [page, setPage] = useState(pageFromHash);
  const [filters, setFilters] = useState<Filters>(() => ({
    start: localDay(session.timezone, -6), end: localDay(session.timezone), camera_id: "", equipment: "", status: "",
  }));
  const [bucket, setBucket] = useState<Bucket>("day");
  const [offset, setOffset] = useState(0);
  const [selection, setSelection] = useState<Occurrence>();
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState("");
  const [live, setLive] = useState(false);
  const [media, setMedia] = useState<{ camera: string; mode: "image" | "webcam"; key: number }>({
    camera: "", mode: "image", key: 0,
  });
  const overview = page === "overview";
  const filteredPage = overview || page === "events" || page === "evidence";
  const limit = overview ? 5 : page === "evidence" ? 9 : 15;
  const criteria = overview ? { ...filters, status: "" as const } : filters;
  const { data: cameras, error: cameraError } = useData<Camera[]>("/cameras", refresh);
  const { data: summary, error: summaryError } = useData<Summary>(
    overview ? `/analytics/summary?${filterQuery(criteria, { bucket })}` : null, refresh,
  );
  const { data: events, error: eventsError } = useData<EventPage>(
    filteredPage ? `/events?${filterQuery(criteria, { limit: String(limit), offset: String(overview ? 0 : offset) })}` : null, refresh,
  );

  useEffect(() => {
    const sync = () => { setPage(pageFromHash()); setOffset(0); };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  useEffect(() => {
    let disposed = false, timer: number | undefined, ws: WebSocket | undefined;
    function connect() {
      if (disposed) return;
      ws = socket("/events/live");
      ws.onopen = () => { setLive(true); setRefresh((value) => value + 1); };
      ws.onmessage = (event) => {
        if (JSON.parse(event.data).type === "event") setRefresh((value) => value + 1);
      };
      ws.onclose = () => {
        if (!disposed) { setLive(false); timer = window.setTimeout(connect, 3000); }
      };
    }
    connect();
    const interval = window.setInterval(() => setRefresh((value) => value + 1), 45_000);
    return () => { disposed = true; clearTimeout(timer); clearInterval(interval); ws?.close(); };
  }, []);

  function go(target: Page) {
    setPage(target); setOffset(0); setError("");
    window.location.hash = target;
    window.scrollTo(0, 0);
  }
  function mediaPage(mode: "image" | "webcam", camera = "") {
    setMedia((current) => ({ mode, camera, key: current.key + 1 }));
    go("media");
  }
  function updateFilters(value: Filters) { setOffset(0); setFilters(value); }
  const update = () => setRefresh((value) => value + 1);
  const errorMessage = error || cameraError || (filteredPage ? eventsError : "") || (overview ? summaryError : "");
  const dateLabel = new Intl.DateTimeFormat("pt-BR", {
    timeZone: session.timezone, weekday: "short", day: "numeric", month: "long", year: "numeric",
  }).format(new Date());

  return <Layout session={session} page={page} go={go} live={live}
    pending={() => { updateFilters({ ...filters, status: "open" }); go("events"); }}
    logout={async () => { try { await logout(); } catch (cause) { setError((cause as Error).message); } }}>
    <div className="intro">
      <div>{overview && <div className="intro-date"><CalendarDays size={15} /> {dateLabel}</div>}
        <h1>{pageCopy[page].title}</h1><p>{pageCopy[page].subtitle}</p></div>
      {(overview || page === "events") && <button className="button primary new-analysis" onClick={() => mediaPage("image")}><Plus size={19} strokeWidth={2.4} /> Nova análise</button>}
    </div>
    {errorMessage && <ErrorNotice message={errorMessage} />}
    {filteredPage && <DateFilters filters={criteria} cameras={cameras ?? []} timezone={session.timezone}
      onChange={updateFilters} advanced={!overview} />}
    {overview && <>
      {summary ? <Suspense fallback={<div className="panel loading" role="status">Carregando gráficos…</div>}>
        <Metrics data={summary} /><MainCharts data={summary} bucket={bucket} changeBucket={setBucket} />
      </Suspense>
        : !summaryError && <div className="panel loading" role="status">Carregando indicadores…</div>}
      <section className="panel recent">
        <div className="panel-heading"><div><h2>Ocorrências recentes</h2><p>Últimas violações no período selecionado</p></div>
          <button className="text-button" onClick={() => { setFilters(criteria); go("events"); }}>Ver ocorrências <ArrowRight size={16} /></button>
        </div>
        {events ? <EventTable entries={events.items.slice(0, 5)} timezone={session.timezone} onSelect={setSelection} />
          : !eventsError && <div className="loading" role="status">Carregando ocorrências…</div>}
      </section>
      {summary && <Suspense><SecondaryCharts data={summary} onCameras={() => go("cameras")} /></Suspense>}
    </>}
    {(page === "events" || page === "evidence") && (events ? <>
      {page === "events" ? <section className="panel recent"><div className="panel-heading"><div><h2>Histórico de ocorrências</h2>
        <p>{number(events.total)} registros neste período</p></div></div>
        <EventTable entries={events.items} timezone={session.timezone} onSelect={setSelection} />
      </section> : <Gallery items={events.items} timezone={session.timezone} onSelect={setSelection} />}
      {events.total > limit && <div className="pagination">
        <button className="icon-button" aria-label="Página anterior" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - limit))}><ChevronLeft size={19} /></button>
        <span>{offset + 1}–{Math.min(offset + limit, events.total)} de {events.total}</span>
        <button className="icon-button" aria-label="Próxima página" disabled={offset + limit >= events.total} onClick={() => setOffset(offset + limit)}><ChevronRight size={19} /></button>
      </div>}
    </> : !eventsError && <div className="panel loading" role="status">Carregando ocorrências…</div>)}
    {page === "cameras" && <CameraPage cameras={cameras ?? []} session={session} useCamera={(id) => mediaPage("webcam", id)} refresh={update} />}
    {page === "media" && <Media key={media.key} cameras={cameras ?? []} session={session} initialCamera={media.camera} initialMode={media.mode} />}
    {page === "settings" && <SettingsPage session={session} />}
    {selection && <EventDetails key={selection.id} item={selection} session={session} close={() => setSelection(undefined)} refresh={update} />}
  </Layout>;
}

function App() {
  const [version, setVersion] = useState(0);
  const { data: session, error } = useData<Session>("/auth/session", version);
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const expire = () => setExpired(true);
    window.addEventListener("session-expired", expire);
    return () => window.removeEventListener("session-expired", expire);
  }, []);
  if (!session) return <div className="login-shell"><div className="login-panel"><Brand />
    {error ? <><ErrorNotice message={error} /><button className="button primary" onClick={() => setVersion(version + 1)}>Tentar novamente</button></>
      : <p role="status">Carregando SafeVision…</p>}</div></div>;
  if (!session.authenticated || expired) return <Login onLogin={() => { setExpired(false); setVersion(version + 1); }} />;
  return <Workspace session={session} logout={async () => {
    await api("/auth/logout", { method: "POST" }); setExpired(true); setVersion(version + 1);
  }} />;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
