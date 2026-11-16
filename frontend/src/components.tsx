import { useEffect, useRef, type ReactNode } from "react";
import { CalendarDays, Camera as CameraIcon, ChevronDown, CircleAlert, HardHat, ImageOff, SlidersHorizontal, X } from "lucide-react";
import {
  dateTime, equipmentName, localDay, percent, statusName, type Camera, type Filters, type Occurrence,
} from "./api";

export function Brand() {
  return <div className="brand"><img src="/favicon.svg" alt="" /><span>Safe<span className="brand-accent">Vision</span><small>MONITORAMENTO DE EPIs</small></span></div>;
}

export function ErrorNotice({ message }: { message: string }) {
  return <div role="alert" className="error-notice"><CircleAlert size={17} />{message}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><ImageOff size={24} /><strong>{title}</strong>{children && <p>{children}</p>}</div>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return <dialog ref={ref} className="modal" onCancel={onClose}
    onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <header><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Fechar"><X size={20} /></button></header>
    <div className="modal-body">{children}</div>
  </dialog>;
}

export function DateFilters({ filters, cameras, timezone, onChange, advanced = false }: {
  filters: Filters; cameras: Camera[]; timezone: string; onChange: (filters: Filters) => void; advanced?: boolean;
}) {
  const today = localDay(timezone);
  const preset = filters.end === today
    ? [7, 14, 30, 90].find((days) => filters.start === localDay(timezone, 1 - days)) : undefined;
  return <div className="filters">
    <div className="filter-label"><SlidersHorizontal size={16} /> <span>Filtros</span></div>
    <label className="select-control"><CalendarDays size={16} /><span className="sr-only">Período</span>
      <select value={preset ?? "custom"} onChange={(event) => {
        const days = Number(event.target.value);
        if (days) onChange({ ...filters, start: localDay(timezone, 1 - days), end: today });
        else onChange({ ...filters, start: today, end: today });
      }}>
        <option value={7}>Últimos 7 dias</option><option value={14}>Últimos 14 dias</option>
        <option value={30}>Últimos 30 dias</option><option value={90}>Últimos 90 dias</option>
        <option value="custom">Personalizado</option>
      </select><ChevronDown size={14} className="select-arrow" />
    </label>
    {preset === undefined && <div className="date-range">
      <label className="sr-only" htmlFor="filter-start">Início</label><input id="filter-start" type="date" value={filters.start}
        max={filters.end} onChange={(event) => event.target.value && onChange({ ...filters, start: event.target.value })} />
      <span>até</span>
      <label className="sr-only" htmlFor="filter-end">Fim</label><input id="filter-end" type="date" value={filters.end}
        min={filters.start} onChange={(event) => event.target.value && onChange({ ...filters, end: event.target.value })} />
    </div>}
    <label className="select-control"><CameraIcon size={16} /><span className="sr-only">Câmera</span>
      <select value={filters.camera_id} onChange={(event) => onChange({ ...filters, camera_id: event.target.value })}>
        <option value="">Todas as câmeras</option>
        {cameras.map((camera) => <option value={camera.id} key={camera.id}>{camera.name}</option>)}
      </select><ChevronDown size={14} className="select-arrow" />
    </label>
    <label className="select-control"><HardHat size={17} /><span className="sr-only">Tipo de EPI</span>
      <select value={filters.equipment} onChange={(event) => onChange({ ...filters, equipment: event.target.value as Filters["equipment"] })}>
        <option value="">Todos os EPIs</option><option value="helmet">Capacete</option><option value="vest">Colete</option>
      </select><ChevronDown size={14} className="select-arrow" />
    </label>
    {advanced && <label className="select-control"><span className="sr-only">Status</span>
      <select value={filters.status} onChange={(event) => onChange({ ...filters, status: event.target.value as Filters["status"] })}>
        <option value="">Todos os status</option>{Object.entries(statusName).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
      </select><ChevronDown size={14} className="select-arrow" />
    </label>}
    {(filters.camera_id || filters.equipment || filters.status || preset !== 7) &&
      <button className="text-button reset-filters" onClick={() => onChange({
        start: localDay(timezone, -6), end: today, equipment: "", camera_id: "", status: "",
      })}>Limpar</button>}
  </div>;
}

export const EquipmentTag = ({ equipment }: { equipment: Occurrence["equipment"] }) =>
  <span className={`equipment ${equipment}`}><i />Sem {equipmentName[equipment].toLowerCase()}</span>;

export const StatusTag = ({ status }: { status: Occurrence["status"] }) =>
  <span className={`status-tag ${status}`}><i />{statusName[status]}</span>;

export function EventTable({ entries, timezone, onSelect }: {
  entries: Occurrence[]; timezone: string; onSelect: (event: Occurrence) => void;
}) {
  if (!entries.length) return <Empty title="Nenhuma ocorrência no período">Ajuste os filtros ou envie um vídeo para análise.</Empty>;
  return <div className="table-scroll"><table><thead><tr>
    <th>Ocorrência</th><th>Câmera</th><th>Data e hora</th><th>Confiança</th><th>Status</th><th><span className="sr-only">Detalhes</span></th>
  </tr></thead><tbody>
    {entries.map((event) => <tr key={event.id} onClick={() => onSelect(event)}>
      <td><div className="event-title">{event.evidence_url
        ? <img src={event.evidence_url} loading="lazy" alt="" />
        : <span className="image-placeholder"><ImageOff size={16} /></span>}
        <div><EquipmentTag equipment={event.equipment} /><small>Pessoa #{event.track_id.toString().padStart(2, "0")}</small></div>
      </div></td>
      <td className="camera-cell">{event.camera_name}</td>
      <td className="muted time-cell">{dateTime(event.occurred_at, timezone)}</td>
      <td><span className="confidence"><span><i style={{ width: percent(event.confidence) }} /></span>{percent(event.confidence)}</span></td>
      <td><StatusTag status={event.status} /></td>
      <td><button className="icon-button row-details" onClick={(e) => { e.stopPropagation(); onSelect(event); }}
        aria-label={`Detalhes da ocorrência de ${event.camera_name}`}>›</button></td>
    </tr>)}
  </tbody></table></div>;
}
