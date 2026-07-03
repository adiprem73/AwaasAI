import { useCallback, useEffect, useRef, useState } from "react";
import { safetyApi } from "../safetyApi.js";

// ════════════════════════════════════════════════════════════════════════════
//  THE GUARDIAN — elderly-alone protective layer
//  ---------------------------------------------------------------------------
//  When a vulnerable person is home ALONE, the Guardian keeps a heightened watch.
//  The deterministic engine raises concerns; the LLM triages to the single most
//  dangerous + relevant one and decides: raise the alarm NOW (extreme) or gently
//  CHECK IN with the person first (less serious) before escalating. The elder can
//  reply by voice or a tap; a reassuring reply stands the alarm down, distress or
//  silence escalates to family.
// ════════════════════════════════════════════════════════════════════════════

const POSTURE = {
  safe: { label: "Calm watch", cls: "border-emerald-500/40 bg-emerald-500/5", text: "text-emerald-300", dot: "bg-emerald-400" },
  watchful: { label: "Watching", cls: "border-sky-500/40 bg-sky-500/5", text: "text-sky-300", dot: "bg-sky-400" },
  concern: { label: "Concern", cls: "border-amber-500/50 bg-amber-500/5", text: "text-amber-300", dot: "bg-amber-400" },
  emergency: { label: "Emergency", cls: "border-red-500/60 bg-red-500/10", text: "text-red-300", dot: "bg-red-500" },
};

function blobToBase64(blob) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onloadend = () => res(String(r.result).split(",")[1]);
    r.onerror = rej;
    r.readAsDataURL(blob);
  });
}

export default function GuardianPanel({ hid, boardKey, buildRequest }) {
  const [decision, setDecision] = useState(null);
  const [busy, setBusy] = useState(false);
  const [verdict, setVerdict] = useState(null); // check-in result
  const [checkBusy, setCheckBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const mrRef = useRef(null);

  // Re-assess whenever the board changes (debounced).
  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const d = await safetyApi.guardianAssess(hid, buildRequest());
        if (!cancelled) { setDecision(d); setVerdict(null); }
      } catch {
        if (!cancelled) setDecision(null);
      } finally {
        if (!cancelled) setBusy(false);
      }
    }, 220);
    return () => { cancelled = true; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boardKey, hid]);

  const respond = useCallback(
    async ({ text, audioBase64 } = {}) => {
      if (!decision) return;
      setCheckBusy(true);
      try {
        const v = await safetyApi.guardianCheckin(hid, {
          text: text || null,
          audio_base64: audioBase64 || null,
          audio_format: "webm",
          person: decision.person,
          concern_detail: decision.flagged?.detail || "",
        });
        setVerdict(v);
      } catch {
        /* ignore */
      } finally {
        setCheckBusy(false);
      }
    },
    [decision, hid],
  );

  const toggleRecord = useCallback(async () => {
    if (recording) { try { mrRef.current?.stop(); } catch { /* noop */ } return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { return; }
    const mr = new MediaRecorder(stream);
    mrRef.current = mr;
    const chunks = [];
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
      const b64 = await blobToBase64(new Blob(chunks, { type: mr.mimeType || "audio/webm" }));
      respond({ audioBase64: b64 });
    };
    mr.start();
    setRecording(true);
    setTimeout(() => { try { mr.state !== "inactive" && mr.stop(); } catch { /* noop */ } }, 6000);
  }, [recording, respond]);

  if (!decision) {
    return (
      <section className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-4 text-[11px] text-slate-500">
        {busy ? "🛡️ Guardian assessing…" : "🛡️ Guardian — set the board to begin."}
      </section>
    );
  }

  const p = POSTURE[decision.posture] || POSTURE.safe;
  const fl = decision.flagged;

  return (
    <section className={["overflow-hidden rounded-2xl border", p.cls].join(" ")}>
      {/* Header / situation */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-rose-500 to-red-600 text-lg shadow">🛡️</span>
        <div className="leading-tight">
          <h2 className="text-sm font-bold text-slate-100">The Guardian</h2>
          <p className="text-[10px] text-slate-400">
            {decision.vigilance
              ? <><span className="font-semibold text-rose-300">{decision.person} is home alone</span> · heightened watch</>
              : "On standby — no vulnerable person alone"}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <span className={["h-2 w-2 rounded-full", p.dot, decision.posture === "emergency" ? "animate-pulse" : ""].join(" ")} />
          <span className={["text-[11px] font-semibold", p.text].join(" ")}>{p.label}</span>
        </div>
      </div>

      <div className="border-t border-slate-800 p-4">
        {/* ── ALL CLEAR ── */}
        {decision.mode === "all_clear" && (
          <p className="text-sm text-emerald-300">✓ {decision.spoken}</p>
        )}

        {/* ── AUTO ALARM ── */}
        {decision.mode === "auto_alarm" && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-red-500/25 px-2 py-0.5 text-[10px] font-black uppercase tracking-wide text-red-200 animate-pulse">🚨 Alarm raised</span>
              {fl && <span className="text-[10px] font-semibold uppercase text-red-300">{fl.type.replace(/_/g, " ")}</span>}
            </div>
            {fl && <p className="text-sm font-semibold text-slate-100">{fl.detail}</p>}
            <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-100">🔊 {decision.spoken}</p>
            {decision.family_message && (
              <div className="rounded-lg border border-red-500/30 bg-slate-950/40 px-3 py-2">
                <p className="text-[10px] font-bold uppercase tracking-wide text-red-300">👪 Family notified</p>
                <p className="text-xs text-slate-200">{decision.family_message}</p>
              </div>
            )}
          </div>
        )}

        {/* ── CHECK IN FIRST ── */}
        {decision.mode === "check_in" && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-200">❔ Checking in first</span>
              {fl && <span className="text-[10px] text-slate-400">{fl.type.replace(/_/g, " ")}</span>}
            </div>
            {fl && <p className="text-xs text-slate-400">{fl.detail}</p>}
            <p className="rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-100">🔊 {decision.checkin_prompt || decision.spoken}</p>

            {!verdict ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] text-slate-500">{decision.person} replies:</span>
                <button onClick={() => respond({ text: "I'm fine, just resting" })} disabled={checkBusy}
                  className="rounded-lg border border-emerald-500/50 bg-emerald-500/10 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50">
                  🟢 I'm fine
                </button>
                <button onClick={() => respond({ text: "Help, I've fallen and I can't get up" })} disabled={checkBusy}
                  className="rounded-lg border border-red-500/50 bg-red-500/10 px-2.5 py-1.5 text-[11px] font-semibold text-red-200 hover:bg-red-500/20 disabled:opacity-50">
                  🔴 I need help
                </button>
                <button onClick={toggleRecord} disabled={checkBusy}
                  className={["rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition disabled:opacity-50",
                    recording ? "border-red-400/70 bg-red-500/20 text-red-200 animate-pulse" : "border-slate-600/60 bg-slate-800/60 text-slate-300 hover:bg-slate-700"].join(" ")}>
                  {recording ? "■ listening" : "🎙️ speak"}
                </button>
                <button onClick={() => respond({ text: "" })} disabled={checkBusy}
                  className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-[11px] text-slate-400 hover:text-slate-200 disabled:opacity-50">
                  ⏱ no response
                </button>
                {checkBusy && <span className="text-[11px] text-slate-500">…</span>}
              </div>
            ) : (
              <div className={["rounded-lg border px-3 py-2", verdict.verdict === "stand_down" ? "border-emerald-500/40 bg-emerald-500/5" : "border-red-500/50 bg-red-500/10"].join(" ")}>
                <p className={["text-[10px] font-bold uppercase tracking-wide", verdict.verdict === "stand_down" ? "text-emerald-300" : "text-red-300"].join(" ")}>
                  {verdict.verdict === "stand_down" ? "✓ Stood down" : "🚨 Escalated to family"}
                </p>
                {verdict.transcript && <p className="text-[10px] italic text-slate-500">heard: “{verdict.transcript}”</p>}
                <p className="text-sm text-slate-100">🔊 {verdict.spoken}</p>
                {verdict.notify_family && verdict.family_message && (
                  <p className="mt-1 text-xs text-red-200">👪 {verdict.family_message}</p>
                )}
                <button onClick={() => setVerdict(null)} className="mt-1 text-[10px] text-slate-500 hover:text-slate-300">↺ reply again</button>
              </div>
            )}
          </div>
        )}

        {/* ── Triage transparency ── */}
        {decision.all_concerns?.length > 0 && (
          <div className="mt-3 border-t border-slate-800 pt-2">
            <p className="text-[10px] text-slate-500">
              Guardian reviewed <span className="text-slate-300">{decision.all_concerns.length}</span> signal(s), flagged the most pressing:
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              {(decision.danger_rank?.length ? decision.danger_rank : decision.all_concerns.map((c) => c.type)).slice(0, 6).map((t, i) => (
                <span key={`${t}-${i}`}
                  className={["rounded-full px-1.5 py-0.5 text-[9px] font-semibold", i === 0 ? "bg-rose-500/20 text-rose-200 ring-1 ring-rose-500/40" : "bg-slate-800 text-slate-400"].join(" ")}>
                  {i === 0 ? "▶ " : ""}{String(t).replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
