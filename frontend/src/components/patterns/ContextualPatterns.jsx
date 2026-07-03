import { useCallback, useMemo, useState } from "react";
import { api } from "../../patternsApi.js";
import { HOUSEHOLDS } from "../../config/houseLayout.js";

// ════════════════════════════════════════════════════════════════════════════
//  AI CONTEXTUAL PATTERNS  (Demo 1)
//  ---------------------------------------------------------------------------
//  The deterministic engine mines UNCONDITIONAL routines ("AC on ~14:30").
//  This panel asks the LLM to propose CONDITIONAL routines it can't express
//  ("AC on ONLY when it's hot"), and the backend re-measures every proposal
//  against real history before returning it — so nothing hallucinated survives.
//
//  The live-context controls (temperature / weekend / who's home) re-flag which
//  patterns apply RIGHT NOW, evaluated client-side so it's instant to demo.
// ════════════════════════════════════════════════════════════════════════════

function humanizeCond(c) {
  if (!c) return "";
  const { feature, op, value } = c;
  if (feature === "temperature_c") return `temperature ${op} ${value}°C`;
  if (feature === "is_weekend")
    return String(value).toLowerCase() === "true" || value === true
      ? "on weekends"
      : "on weekdays";
  if (feature === "season") return `in ${value}`;
  if (feature === "dow") return `on ${value}`;
  if (typeof feature === "string" && feature.startsWith("arrived:"))
    return `when ${feature.split(":")[1]} comes home`;
  if (typeof feature === "string" && feature.startsWith("active:"))
    return `when ${feature.split(":")[1]} is home`;
  return `${feature} ${op} ${value}`;
}

// Client-side mirror of day_features.condition_active so the slider is instant.
function condActiveNow(cond, ctx) {
  if (!cond) return false;
  const { feature, op, value } = cond;
  let lhs;
  if (feature === "temperature_c") lhs = ctx.temperatureC;
  else if (feature === "is_weekend") lhs = ctx.isWeekend;
  else if (typeof feature === "string" && (feature.startsWith("arrived:") || feature.startsWith("active:")))
    lhs = ctx.occupants.has(feature.split(":")[1]);
  else return false;
  if (lhs === null || lhs === undefined) return false;

  let rhs = value;
  if (typeof lhs === "boolean")
    rhs = typeof value === "string" ? ["true", "1", "yes"].includes(value.toLowerCase()) : Boolean(value);
  if (typeof lhs === "number") rhs = Number(value);

  switch (op) {
    case "==": return lhs === rhs;
    case "!=": return lhs !== rhs;
    case ">": return lhs > rhs;
    case "<": return lhs < rhs;
    case ">=": return lhs >= rhs;
    case "<=": return lhs <= rhs;
    default: return false;
  }
}

function evidenceLine(p) {
  const e = p.evidence || {};
  if ((p.kind || e.kind) === "time_shift") {
    return `Usual ${e.usual_time_when_false} → ${e.usual_time_when_true} (+${e.time_shift_minutes} min) when the condition holds.`;
  }
  const t = Math.round((e.rate_when_true ?? 0) * 100);
  const f = Math.round((e.rate_when_false ?? 0) * 100);
  return `Happens ${t}% of ${e.days_condition_true} matching days · only ${f}% of the ${e.days_condition_false} others.`;
}

export default function ContextualPatterns({ householdId }) {
  const people = HOUSEHOLDS[householdId]?.people || [];
  const [temperatureC, setTemperatureC] = useState(34);
  const [isWeekend, setIsWeekend] = useState(false);
  const [occupants, setOccupants] = useState(() => new Set(people));
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const ctx = useMemo(
    () => ({ temperatureC, isWeekend, occupants }),
    [temperatureC, isWeekend, occupants],
  );

  const generate = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.contextual(householdId, {
        temperatureC,
        isWeekend,
        occupants: [...occupants],
      });
      setData(res);
    } catch (e) {
      setError(e.message);
      setData(null);
    } finally {
      setBusy(false);
    }
  }, [householdId, temperatureC, isWeekend, occupants]);

  const toggleOccupant = (p) =>
    setOccupants((prev) => {
      const n = new Set(prev);
      if (n.has(p)) n.delete(p);
      else n.add(p);
      return n;
    });

  const patterns = data?.patterns || [];

  return (
    <section className="rounded-2xl border border-fuchsia-500/30 bg-slate-900/50 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-fuchsia-500 to-purple-600 text-base shadow">
          ✨
        </span>
        <div className="leading-tight">
          <h2 className="text-sm font-bold text-slate-100">AI Contextual Patterns</h2>
          <p className="text-[10px] text-slate-400">
            Conditional routines the statistical engine can’t express — LLM proposes, real history verifies
          </p>
        </div>
        <button
          onClick={generate}
          disabled={busy}
          className="ml-auto rounded-lg border border-fuchsia-400/60 bg-fuchsia-500/15 px-3 py-1.5 text-xs font-semibold text-fuchsia-200 transition hover:bg-fuchsia-500/25 disabled:opacity-50"
        >
          {busy ? "… Reasoning" : "✨ Generate contextual patterns"}
        </button>
      </div>

      {/* Live-context controls */}
      <div className="mb-3 flex flex-wrap items-center gap-4 rounded-xl border border-slate-700/50 bg-slate-950/40 px-3 py-2">
        <label className="flex items-center gap-2 text-[11px] text-slate-400">
          🌡️ Temp
          <input
            type="range" min="20" max="42" step="1"
            value={temperatureC}
            onChange={(e) => setTemperatureC(Number(e.target.value))}
            className="h-1.5 w-32 cursor-pointer appearance-none rounded-full bg-slate-700 accent-fuchsia-500"
          />
          <span className="w-10 font-mono text-slate-200">{temperatureC}°C</span>
        </label>
        <button
          onClick={() => setIsWeekend((w) => !w)}
          className={[
            "rounded-lg border px-2.5 py-1 text-[11px] font-semibold transition",
            isWeekend
              ? "border-amber-400/60 bg-amber-500/20 text-amber-200"
              : "border-slate-700 bg-slate-800/60 text-slate-300",
          ].join(" ")}
        >
          {isWeekend ? "📅 Weekend" : "📅 Weekday"}
        </button>
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-slate-500">Home:</span>
          {people.map((p) => {
            const on = occupants.has(p);
            return (
              <button
                key={p}
                onClick={() => toggleOccupant(p)}
                className={[
                  "rounded-full px-2 py-0.5 text-[10px] font-medium capitalize transition",
                  on
                    ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40"
                    : "bg-slate-700/40 text-slate-500",
                ].join(" ")}
              >
                {on ? "🟢" : "⚪"} {p}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
      )}

      {data && (
        <p className="mb-2 flex items-center gap-2 text-[11px] text-slate-400">
          <span
            className={[
              "rounded px-1.5 py-0.5 font-semibold",
              data.llm_powered ? "bg-fuchsia-500/15 text-fuchsia-300" : "bg-slate-700/50 text-slate-400",
            ].join(" ")}
          >
            {data.llm_powered ? "🤖 LLM-generated" : "⚙️ deterministic fallback"}
          </span>
          proposed {data.generated} · <span className="text-emerald-300">verified {data.verified}</span> against{" "}
          {data.base_pattern_count} base patterns
        </p>
      )}

      {!data && !busy && (
        <p className="rounded-lg bg-slate-800/40 px-3 py-6 text-center text-xs text-slate-500">
          Hit <span className="text-fuchsia-300">Generate</span> — the LLM reads 30 days of context
          (weather, weekday, who’s home) and proposes conditional routines; only rules real history
          backs are shown.
        </p>
      )}

      {data && patterns.length === 0 && (
        <p className="rounded-lg bg-slate-800/40 px-3 py-4 text-center text-xs text-slate-500">
          No verified conditional patterns for this home.
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {patterns.map((p) => {
          const active = condActiveNow(p.condition, ctx);
          return (
            <li
              key={p.pattern_id}
              className={[
                "rounded-xl border px-3 py-2.5 transition",
                active
                  ? "border-emerald-400/60 bg-emerald-500/10 shadow-[0_0_0_1px_rgba(16,185,129,0.25)]"
                  : "border-slate-700/60 bg-slate-950/40",
              ].join(" ")}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-100">{p.human_label}</p>
                  <p className="text-xs text-slate-300">{p.claim}</p>
                </div>
                {active && (
                  <span className="shrink-0 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-300 ring-1 ring-emerald-500/40">
                    ● active now
                  </span>
                )}
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px]">
                <span className="rounded bg-fuchsia-500/15 px-1.5 py-0.5 font-medium text-fuchsia-300">
                  {humanizeCond(p.condition)}
                </span>
                <span className="rounded bg-slate-700/50 px-1.5 py-0.5 text-slate-300">
                  {p.kind === "time_shift" ? "⏱ time-shift" : "🔀 conditional"}
                </span>
                <span className="text-slate-500">
                  verified confidence{" "}
                  <span className="font-semibold text-emerald-300">
                    {Math.round(p.confidence * 100)}%
                  </span>
                </span>
              </div>
              <p className="mt-1 text-[10px] text-slate-500">{evidenceLine(p)}</p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}