import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/api/dashboard/ws`;
}

function formatTime(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatLogTime(ts) {
  return new Date(ts * 1000).toLocaleString("fr-FR");
}

export default function App() {
  const [snapshot, setSnapshot] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [trafficHours, setTrafficHours] = useState(24);
  const [trafficSeries, setTrafficSeries] = useState([]);
  const [logs, setLogs] = useState([]);
  const [logUser, setLogUser] = useState("");
  const [logFrom, setLogFrom] = useState("");
  const [logTo, setLogTo] = useState("");
  const [limitInput, setLimitInput] = useState("");
  const [windowInput, setWindowInput] = useState("");
  const [configSaving, setConfigSaving] = useState(false);
  const [configMessage, setConfigMessage] = useState("");

  useEffect(() => {
    let ws;
    let alive = true;
    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => alive && setWsConnected(true);
      ws.onclose = () => {
        if (!alive) return;
        setWsConnected(false);
        setTimeout(connect, 2500);
      };
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          setSnapshot(data);
        } catch {
          /* ignore */
        }
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => {
      alive = false;
      ws?.close();
    };
  }, []);

  const loadTraffic = useCallback(async (hours) => {
    const r = await fetch(`/api/dashboard/traffic?hours=${hours}`);
    if (!r.ok) return;
    const data = await r.json();
    setTrafficSeries(data.series || []);
  }, []);

  useEffect(() => {
    loadTraffic(trafficHours);
  }, [trafficHours, loadTraffic]);

  useEffect(() => {
    (async () => {
      const r = await fetch("/api/dashboard/logs?limit=100");
      if (!r.ok) return;
      const data = await r.json();
      setLogs(data.items || []);
    })();
  }, []);

  useEffect(() => {
    if (snapshot?.config) {
      setLimitInput(String(snapshot.config.limit));
      setWindowInput(String(snapshot.config.window_seconds));
    }
  }, [snapshot?.config?.limit, snapshot?.config?.window_seconds]);

  const chartData = useMemo(() => {
    return trafficSeries.map((row) => ({
      ...row,
      label: formatTime(row.ts),
      allowed: Math.max(0, row.requests - row.blocked),
    }));
  }, [trafficSeries]);

  const blockedUsers = useMemo(() => {
    if (!snapshot?.users) return [];
    return snapshot.users.filter((u) => u.status === "blocked");
  }, [snapshot?.users]);

  const alertKeys = useMemo(() => {
    if (!snapshot?.alerts) return [];
    return Object.entries(snapshot.alerts)
      .filter(([, v]) => v)
      .map(([k]) => k);
  }, [snapshot?.alerts]);

  const fetchLogs = async () => {
    const params = new URLSearchParams();
    if (logUser.trim()) params.set("user", logUser.trim());
    if (logFrom) {
      const t = Date.parse(logFrom);
      if (!Number.isNaN(t)) params.set("from", String(t / 1000));
    }
    if (logTo) {
      const t = Date.parse(logTo);
      if (!Number.isNaN(t)) params.set("to", String(t / 1000));
    }
    const r = await fetch(`/api/dashboard/logs?${params}`);
    if (!r.ok) return;
    const data = await r.json();
    setLogs(data.items || []);
  };

  const applyConfig = async () => {
    setConfigSaving(true);
    setConfigMessage("");
    const body = {};
    const li = parseInt(limitInput, 10);
    const wi = parseInt(windowInput, 10);
    if (!Number.isNaN(li)) body.limit = li;
    if (!Number.isNaN(wi)) body.window_seconds = wi;
    try {
      const r = await fetch("/api/dashboard/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        const cfg = await r.json();
        setConfigMessage(`Limites mises à jour : ${cfg.limit} req / ${cfg.window_seconds}s`);
      } else {
        setConfigMessage("Échec de la mise à jour");
      }
    } catch {
      setConfigMessage("Erreur réseau");
    } finally {
      setConfigSaving(false);
    }
  };

  const g = snapshot?.global;
  const cfg = snapshot?.config;

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "1.25rem 1rem 3rem" }}>
      <header className="header-bar">
        <div>
          <h1>Dashboard rate limiting</h1>
          <p className="muted">
            Trafic API, quotas Redis et journaux. Les routes du dashboard ne sont pas soumises au rate
            limit pour rester accessible.
          </p>
        </div>
        <div className={`pill-live ${wsConnected ? "" : "off"}`}>
          {wsConnected ? "Temps réel (WebSocket)" : "Reconnexion…"}
        </div>
      </header>

      {(alertKeys.length > 0 || blockedUsers.length > 0) && (
        <div className="alert-banner">
          <strong>Alertes :</strong>
          <span>
            {blockedUsers.length > 0
              ? `${blockedUsers.length} utilisateur(s) à la limite ou bloqué(s). `
              : ""}
            {alertKeys.length > 0
              ? `Dépassement signalé pour : ${alertKeys.slice(0, 8).join(", ")}${alertKeys.length > 8 ? "…" : ""}`
              : null}
          </span>
        </div>
      )}

      <div className="grid-cards">
        <div className="card">
          <div className="card-label">Requêtes / minute (en cours)</div>
          <div className="card-value">{g?.requests_this_minute ?? "—"}</div>
          <div className="card-sub mono">Minute démarrée : {g?.minute_start ? formatTime(g.minute_start) : "—"}</div>
        </div>
        <div className="card">
          <div className="card-label">429 / minute</div>
          <div className="card-value" style={{ color: "var(--danger)" }}>
            {g?.blocked_this_minute ?? "—"}
          </div>
        </div>
        <div className="card">
          <div className="card-label">Utilisateurs actifs</div>
          <div className="card-value">{g?.active_users ?? "—"}</div>
          <div className="card-sub">Activité sur les 5 dernières minutes</div>
        </div>
        <div className="card">
          <div className="card-label">Quota configuré</div>
          <div className="card-value mono" style={{ fontSize: "1.25rem" }}>
            {cfg ? `${cfg.limit} / ${cfg.window_seconds}s` : "—"}
          </div>
        </div>
      </div>

      <section className="section">
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>Évolution du trafic</h2>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              Historique :
            </span>
            <select value={trafficHours} onChange={(e) => setTrafficHours(Number(e.target.value))}>
              <option value={24}>24 heures</option>
              <option value={72}>3 jours</option>
              <option value={168}>7 jours</option>
            </select>
          </div>
        </div>
        <div style={{ width: "100%", height: 320, marginTop: "0.5rem" }}>
          <ResponsiveContainer>
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fill: "#8b98ad", fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis tick={{ fill: "#8b98ad", fontSize: 11 }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: "#141922", border: "1px solid #2a3344", borderRadius: 8 }}
                labelFormatter={(_, payload) => (payload?.[0]?.payload?.label ? String(payload[0].payload.label) : "")}
              />
              <Legend />
              <Line type="monotone" dataKey="requests" name="Total req" stroke="#5b9cf5" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="allowed" name="Acceptées" stroke="#3dcf8e" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="blocked" name="429" stroke="#f05b5b" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="section">
        <h2>Limites en direct</h2>
        <div className="config-form">
          <div className="field">
            <label htmlFor="lim">Max requêtes / fenêtre</label>
            <input id="lim" type="number" min={1} value={limitInput} onChange={(e) => setLimitInput(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="win">Fenêtre (secondes)</label>
            <input id="win" type="number" min={1} value={windowInput} onChange={(e) => setWindowInput(e.target.value)} />
          </div>
          <button type="button" onClick={applyConfig} disabled={configSaving}>
            {configSaving ? "Enregistrement…" : "Appliquer"}
          </button>
        </div>
        {configMessage && <p className="muted" style={{ marginTop: "0.75rem" }}>{configMessage}</p>}
      </section>

      <section className="section">
        <h2>Par utilisateur / IP</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th>Dans la fenêtre</th>
                <th>Limite</th>
                <th>Restantes</th>
                <th>Total enregistré</th>
                <th>429 cumulés</th>
                <th>Statut</th>
              </tr>
            </thead>
            <tbody>
              {(snapshot?.users || []).length === 0 && (
                <tr>
                  <td colSpan={7} style={{ color: "var(--muted)" }}>
                    Aucun trafic métier enregistré pour l’instant.
                  </td>
                </tr>
              )}
              {(snapshot?.users || []).map((u) => (
                <tr key={u.client_key} className={u.status === "blocked" ? "row-blocked" : ""}>
                  <td className="mono">{u.client_key}</td>
                  <td>{u.usage}</td>
                  <td>{u.limit}</td>
                  <td>{u.remaining}</td>
                  <td>{u.total_recorded}</td>
                  <td>{u.blocked_hits}</td>
                  <td>
                    <span className={u.status === "blocked" ? "badge badge-blocked" : "badge badge-ok"}>
                      {u.status === "blocked" ? "Bloqué" : "OK"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>Journaux des requêtes</h2>
        <div className="filters">
          <label className="filter">
            Utilisateur / IP
            <input value={logUser} onChange={(e) => setLogUser(e.target.value)} placeholder="ex. Ahmed" />
          </label>
          <label className="filter">
            Depuis
            <input type="datetime-local" value={logFrom} onChange={(e) => setLogFrom(e.target.value)} />
          </label>
          <label className="filter">
            Jusqu’à
            <input type="datetime-local" value={logTo} onChange={(e) => setLogTo(e.target.value)} />
          </label>
          <button type="button" onClick={fetchLogs}>
            Filtrer
          </button>
          <button type="button" className="secondary" onClick={() => { setLogUser(""); setLogFrom(""); setLogTo(""); setLogs([]); }}>
            Réinitialiser
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Horodatage</th>
                <th>Utilisateur / IP</th>
                <th>Endpoint</th>
                <th>Code</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ color: "var(--muted)" }}>
                    Aucune entrée pour l’instant — le journal se remplit au fur et à mesure des appels API métier.
                  </td>
                </tr>
              )}
              {logs.map((row, i) => (
                <tr key={`${row.ts}-${i}`} className={row.status_code === 429 ? "row-blocked" : ""}>
                  <td className="mono">{formatLogTime(row.ts)}</td>
                  <td className="mono">{row.client_key}</td>
                  <td className="mono">{row.path}</td>
                  <td>{row.status_code}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
