import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Camera, HardHat, ShieldAlert, Shirt } from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { number, percent, type Bucket, type Summary } from "./api";
import { Empty } from "./components";

const teal = "#0da789";
const blue = "#6884ee";

export function Metrics({ data }: { data: Summary }) {
  const delta = data.total - data.previous_total;
  const categories = data.total || 1;
  const change = data.previous_total ? `${percent(Math.abs(delta) / data.previous_total)}`
    : delta ? `+${delta}` : "0%";
  return <section className="metrics" aria-label="Indicadores de segurança">
    <article className="panel metric">
      <div className="metric-top"><span className="metric-icon purple"><ShieldAlert size={21} /></span><span className="metric-note">NO PERÍODO</span></div>
      <span className="metric-label">Total de violações</span><strong>{number(data.total)}</strong>
      <span className="metric-footer"><span className={`trend ${delta > 0 ? "trend-up" : ""}`}>{delta > 0 ? <ArrowUpRight size={14} /> : delta < 0 ? <ArrowDownRight size={14} /> : <Activity size={13} />}{change}</span> vs. período anterior</span>
    </article>
    <article className="panel metric">
      <div className="metric-top"><span className="metric-icon orange"><HardHat size={22} /></span></div>
      <span className="metric-label">Sem capacete</span><strong>{number(data.helmet)}</strong>
      <span className="metric-footer"><i className="point-dot teal" />{percent(data.helmet / categories)} das violações</span>
    </article>
    <article className="panel metric">
      <div className="metric-top"><span className="metric-icon blue"><Shirt size={21} /></span></div>
      <span className="metric-label">Sem colete</span><strong>{number(data.vest)}</strong>
      <span className="metric-footer"><i className="point-dot blue" />{percent(data.vest / categories)} das violações</span>
    </article>
    <article className="panel metric">
      <div className="metric-top"><span className="metric-icon mint"><Camera size={21} /></span></div>
      <span className="metric-label">Câmeras ativas</span><strong>{data.cameras_active}<span className="metric-denom"> / {data.cameras_total}</span></strong>
      <span className="metric-footer"><i className="point-dot teal" /><span>Atividade recente</span></span>
    </article>
  </section>;
}

const axis = { fontSize: 11, fill: "#66748a" };
const popup = { borderRadius: 10, borderColor: "#e4e9f1", fontSize: 12, boxShadow: "0 3px 14px #0f1b3214" };
const labelDate = (value: string, monthly = false) => new Intl.DateTimeFormat("pt-BR", {
  timeZone: "UTC", ...(monthly ? { month: "short", year: "2-digit" } : { day: "2-digit", month: "short" }),
}).format(new Date(value + "T12:00:00Z")).replace(" de ", " ").replace(".", "");

export function MainCharts({ data, bucket, changeBucket }: {
  data: Summary; bucket: Bucket; changeBucket: (bucket: Bucket) => void;
}) {
  const slices = [{ name: "Sem capacete", value: data.helmet, color: teal }, { name: "Sem colete", value: data.vest, color: blue }];
  return <section className="chart-grid">
    <article className="panel chart-card timeline-card">
      <div className="panel-heading">
        <div><h2>Tendência de violações</h2><p>Ocorrências ao longo do período</p></div>
        <div className="segmented" aria-label="Agrupamento do gráfico">
          {([["day", "Dia"], ["week", "Semana"], ["month", "Mês"]] as const).map(([id, label]) =>
            <button key={id} type="button" className={bucket === id ? "active" : ""} aria-pressed={bucket === id}
              onClick={() => changeBucket(id)}>{label}</button>)}
        </div>
      </div>
      <div className="chart-legend"><span><i className="point-dot teal" />Sem capacete</span><span><i className="point-dot blue" />Sem colete</span></div>
      <div className="line-chart" role="img" aria-label="Série histórica de violações por equipamento">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <AreaChart data={data.timeline} margin={{ top: 8, left: -22, right: 10, bottom: 0 }}>
            <defs>
              <linearGradient id="fillHelmet" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={teal} stopOpacity={0.18} /><stop offset="100%" stopColor={teal} stopOpacity={0.015} /></linearGradient>
              <linearGradient id="fillVest" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={blue} stopOpacity={0.13} /><stop offset="100%" stopColor={blue} stopOpacity={0.015} /></linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="#e8edf4" strokeDasharray="4 4" />
            <XAxis dataKey="date" tickFormatter={(value) => labelDate(value, bucket === "month")} tick={axis} axisLine={false} tickLine={false} tickMargin={10} minTickGap={15} />
            <YAxis tick={axis} axisLine={false} tickLine={false} allowDecimals={false} domain={[0, (value: number) => Math.max(value, 4)]} />
            <Tooltip contentStyle={popup} labelFormatter={(value) => labelDate(String(value), bucket === "month")} />
            <Area name="Sem capacete" type="monotone" dataKey="helmet" stroke={teal} strokeWidth={2.6} fill="url(#fillHelmet)" activeDot={{ r: 5 }} isAnimationActive={false} />
            <Area name="Sem colete" type="monotone" dataKey="vest" stroke={blue} strokeWidth={2.3} fill="url(#fillVest)" activeDot={{ r: 5 }} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </article>
    <article className="panel chart-card distribution">
      <div className="panel-heading"><div><h2>Distribuição por EPI</h2><p>Tipos de violações no período</p></div></div>
      <div className="donut" role="img" aria-label={`${data.helmet} sem capacete e ${data.vest} sem colete`}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <PieChart><Pie data={data.total ? slices : [{ name: "Sem dados", value: 1, color: "#eef2f7" }]}
            dataKey="value" nameKey="name" innerRadius="72%" outerRadius="95%" paddingAngle={data.helmet && data.vest ? 4 : 0}
            cornerRadius={3} startAngle={90} endAngle={-270} stroke="none" isAnimationActive={false}>
            {(data.total ? slices : [{ color: "#eef2f7" }]).map((slice) => <Cell key={slice.color} fill={slice.color} />)}
          </Pie></PieChart>
        </ResponsiveContainer>
        <div className="donut-number"><strong>{number(data.total)}</strong><span>Total</span></div>
      </div>
      <div className="donut-legend">{slices.map((slice) => <div key={slice.name}><span><i className="point-dot" style={{ background: slice.color }} />{slice.name}</span><strong>{percent(slice.value / (data.total || 1))}</strong></div>)}</div>
    </article>
  </section>;
}

export function SecondaryCharts({ data, onCameras }: { data: Summary; onCameras: () => void }) {
  const busiest = data.hours.reduce((peak, item) => item.count > peak.count ? item : peak, { count: 0, hour: 0 });
  return <section className="chart-grid secondary">
    <article className="panel chart-card">
      <div className="panel-heading"><div><h2>Ocorrências por câmera</h2><p>Comparativo no período selecionado</p></div>
        <button className="text-button" onClick={onCameras}>Câmeras <ArrowRight size={15} /></button>
      </div>
      {data.cameras.length ? <div className="camera-bars">{data.cameras.map((camera) =>
        <div key={camera.id}><span>{camera.name}</span><div><i style={{ width: percent(camera.count / (data.cameras[0].count || 1)) }} /></div><strong>{camera.count}</strong></div>,
      )}</div> : <Empty title="Nenhuma câmera no período" />}
    </article>
    <article className="panel chart-card">
      <div className="panel-heading"><div><h2>Horários de maior incidência</h2>
        <p>{busiest.count ? `Pico às ${String(busiest.hour).padStart(2, "0")}h · ${busiest.count} ocorrências` : "Ocorrências por hora local"}</p></div></div>
      <div className="hour-chart">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart data={data.hours} margin={{ top: 7, left: -22, right: 4 }}>
            <CartesianGrid vertical={false} stroke="#e8edf4" strokeDasharray="4 4" />
            <XAxis dataKey="hour" tickFormatter={(hour) => `${hour}h`} interval={3} tick={axis} axisLine={false} tickLine={false} />
            <YAxis tick={axis} allowDecimals={false} axisLine={false} tickLine={false} />
            <Tooltip labelFormatter={(hour) => `${hour}h`} contentStyle={popup} />
            <Bar dataKey="count" name="Ocorrências" fill={teal} radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </article>
  </section>;
}
