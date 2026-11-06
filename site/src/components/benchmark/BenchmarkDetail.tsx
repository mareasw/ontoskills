import React, { useMemo } from 'react';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface AttemptDetail {
  attempt: number;
  reward: number;
  error: string | null;
  n_tool_calls: number;
  tool_calls: Record<string, number>;
  duration_sec: number;
  counted: boolean;
}

export interface CaseInfo {
  engine: string;
  model: string;
  mode: string;
  hints: boolean;
  best_reward: number;
  passed: boolean;
  attempts: AttemptDetail[];
  attempts_completed: number;
}

export interface TaskData {
  task_id: string;
  cases: Record<string, CaseInfo>;
  best_reward: number;
}

interface DetailProps {
  task: TaskData;
  onBack: () => void;
}

/* ------------------------------------------------------------------ */
/* Colors                                                              */
/* ------------------------------------------------------------------ */

const PASS = '#85f496';
const PARTIAL = '#fbbf24';
const FAIL = '#6b7280';
const TRAD = '#9763e1';
const ONTO = '#52c7e8';
const BASE = '#888';

function modeColor(mode: string): string {
  if (mode === 'baseline') return BASE;
  if (mode === 'acp') return TRAD;
  return ONTO;
}

function modeLabel(mode: string, hints: boolean): string {
  const h = hints ? '+hints' : '+nohints';
  return `${mode}${h}`;
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function rewardCell(v: number) {
  if (v >= 1.0) return <span style={{ color: PASS, fontWeight: 700 }}>PASS</span>;
  if (v > 0) return <span style={{ color: PARTIAL, fontWeight: 700 }}>{(v * 100).toFixed(0)}%</span>;
  return <span style={{ color: FAIL }}>-</span>;
}

function fmtDur(sec: number): string {
  if (sec >= 3600) return `${(sec / 3600).toFixed(1)}h`;
  if (sec >= 60) return `${(sec / 60).toFixed(0)}m ${(sec % 60).toFixed(0)}s`;
  return `${sec.toFixed(0)}s`;
}

function fmtToolCalls(tc: Record<string, number>): string {
  return Object.entries(tc)
    .sort((a, b) => b[1] - a[1])
    .map(([t, n]) => `${t}:${n}`)
    .join(', ') || '-';
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export default function BenchmarkDetail({ task, onBack }: DetailProps) {
  const caseEntries = useMemo(() => Object.entries(task.cases), [task]);

  return (
    <div style={{
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: 24,
      marginBottom: 24,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <button onClick={onBack} style={{
          background: 'none', border: '1px solid var(--border)', borderRadius: 6,
          padding: '4px 12px', cursor: 'pointer', color: 'var(--text-secondary)',
          fontSize: 13,
        }}>← Back</button>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace" }}>
          {task.task_id}
        </h3>
      </div>

      {/* Cases summary table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 20 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid var(--border)' }}>
            <th style={{ textAlign: 'left', padding: '8px', fontWeight: 600 }}>Case</th>
            <th style={{ textAlign: 'center', padding: '8px', fontWeight: 600 }}>Engine</th>
            <th style={{ textAlign: 'center', padding: '8px', fontWeight: 600 }}>Model</th>
            <th style={{ textAlign: 'center', padding: '8px', fontWeight: 600 }}>Reward</th>
            <th style={{ textAlign: 'center', padding: '8px', fontWeight: 600 }}>Attempts</th>
            <th style={{ textAlign: 'center', padding: '8px', fontWeight: 600 }}>Tool Calls</th>
            <th style={{ textAlign: 'center', padding: '8px', fontWeight: 600 }}>Avg Duration</th>
          </tr>
        </thead>
        <tbody>
          {caseEntries.map(([key, ci]) => {
            const avgDur = ci.attempts.length > 0
              ? ci.attempts.reduce((s, a) => s + a.duration_sec, 0) / ci.attempts.length
              : 0;
            const totalTc = ci.attempts.reduce((s, a) => s + a.n_tool_calls, 0);
            return (
              <tr key={key} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <td style={{ padding: '8px', color: modeColor(ci.mode), fontWeight: 600 }}>
                  {modeLabel(ci.mode, ci.hints)}
                </td>
                <td style={{ textAlign: 'center', padding: '8px', fontSize: 12 }}>{ci.engine}</td>
                <td style={{ textAlign: 'center', padding: '8px', fontSize: 11 }}>{ci.model}</td>
                <td style={{ textAlign: 'center', padding: '8px' }}>{rewardCell(ci.best_reward)}</td>
                <td style={{ textAlign: 'center', padding: '8px' }}>
                  {ci.attempts_completed}/{ci.attempts.length}
                </td>
                <td style={{ textAlign: 'center', padding: '8px', fontSize: 11 }}>{totalTc}</td>
                <td style={{ textAlign: 'center', padding: '8px', fontSize: 11 }}>{fmtDur(avgDur)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Attempts per case */}
      {caseEntries.map(([key, ci]) => (
        <div key={key} style={{ marginBottom: 16 }}>
          <h4 style={{ margin: '8px 0', fontSize: 14, color: modeColor(ci.mode) }}>
            {modeLabel(ci.mode, ci.hints)} — Attempts
          </h4>
          {ci.attempts.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No attempt data available for this case.
            </p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600 }}>#</th>
                  <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Reward</th>
                  <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Tools</th>
                  <th style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>Duration</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600 }}>Error</th>
                </tr>
              </thead>
              <tbody>
                {ci.attempts.map((att) => (
                  <tr key={att.attempt} style={{
                    borderBottom: '1px solid rgba(255,255,255,0.03)',
                    background: att.reward >= 1.0 ? 'rgba(133,244,150,0.05)' : 'transparent',
                  }}>
                    <td style={{ padding: '6px 8px', fontWeight: 600 }}>{att.attempt}</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}>{rewardCell(att.reward)}</td>
                    <td style={{ padding: '6px 8px', fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>
                      {fmtToolCalls(att.tool_calls)}
                    </td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontSize: 11 }}>{fmtDur(att.duration_sec)}</td>
                    <td style={{
                      padding: '6px 8px', fontSize: 11,
                      color: att.error ? '#f87171' : 'var(--text-muted)',
                      maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {att.error || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  );
}
