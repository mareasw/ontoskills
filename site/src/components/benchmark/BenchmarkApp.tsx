import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  CartesianGrid, LabelList,
} from 'recharts';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface TaskResult {
  task_id: string;
  traditional_reward: number;
  ontoskills_reward: number;
  traditional_passed: boolean;
  ontoskills_passed: boolean;
}

interface Summary {
  pass_rate: number;
  avg_reward: number;
  tasks_passed: number;
  total_tasks: number;
  avg_input_tokens: number;
  avg_output_tokens: number;
  total_cost_usd: number;
}

interface ComparisonData {
  benchmark: string;
  model: string;
  date: string;
  traditional: Summary;
  ontoskills: Summary;
  per_task: TaskResult[];
}

/* ------------------------------------------------------------------ */
/* Embedded data                                                       */
/* ------------------------------------------------------------------ */

const DATA: ComparisonData = {
  "benchmark": "skillsbench",
  "model": "glm-5.1",
  "date": "2026-04-28",
  "traditional": {
    "pass_rate": 0.4, "avg_reward": 0.4, "tasks_passed": 4, "total_tasks": 10,
    "avg_input_tokens": 17199, "avg_output_tokens": 7279, "total_cost_usd": 3.97,
    "tasks_partial": 0, "tasks_failed": 6,
  },
  "ontoskills": {
    "pass_rate": 0.5, "avg_reward": 0.52, "tasks_passed": 5, "total_tasks": 10,
    "avg_input_tokens": 14680, "avg_output_tokens": 4709, "total_cost_usd": 2.92,
    "tasks_partial": 1, "tasks_failed": 4,
  },
  "per_task": [
    {"task_id": "reserves-at-risk-calc", "traditional_reward": 0.0, "ontoskills_reward": 0.2, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "offer-letter-generator", "traditional_reward": 1.0, "ontoskills_reward": 1.0, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "lab-unit-harmonization", "traditional_reward": 0.0, "ontoskills_reward": 0.0, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "travel-planning", "traditional_reward": 1.0, "ontoskills_reward": 1.0, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "paper-anonymizer", "traditional_reward": 0.0, "ontoskills_reward": 1.0, "traditional_passed": false, "ontoskills_passed": true},
    {"task_id": "flood-risk-analysis", "traditional_reward": 0.0, "ontoskills_reward": 0.0, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "3d-scan-calc", "traditional_reward": 1.0, "ontoskills_reward": 1.0, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "exceltable-in-ppt", "traditional_reward": 1.0, "ontoskills_reward": 1.0, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "fix-visual-stability", "traditional_reward": 0.0, "ontoskills_reward": 0.0, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "gh-repo-analytics", "traditional_reward": 0.0, "ontoskills_reward": 0.0, "traditional_passed": false, "ontoskills_passed": false},
  ],
};

/* ------------------------------------------------------------------ */
/* Model pricing                                                       */
/* ------------------------------------------------------------------ */

interface ModelPrice {
  label: string;
  input: number;   // $/MTok
  output: number;  // $/MTok
  used: boolean;   // true = the model actually ran the benchmark
}

const MODELS: Record<string, ModelPrice> = {
  "glm-5.1":        { label: "GLM-5.1",         input: 1.40, output: 4.40, used: true },
  "glm-5":          { label: "GLM-5",            input: 1.00, output: 3.20, used: false },
  "glm-5-turbo":    { label: "GLM-5 Turbo",      input: 1.20, output: 4.00, used: false },
  "glm-4.7":        { label: "GLM-4.7",          input: 0.60, output: 2.20, used: false },
  "claude-opus":    { label: "Claude Opus 4.7",   input: 15.00, output: 75.00, used: false },
  "claude-sonnet":  { label: "Claude Sonnet 4.6", input: 3.00, output: 15.00, used: false },
  "claude-haiku":   { label: "Claude Haiku 4.5",  input: 0.80, output: 4.00, used: false },
  "gpt-5.4":        { label: "GPT-5.4",           input: 2.50, output: 15.00, used: false },
  "gpt-5.4-mini":   { label: "GPT-5.4 mini",      input: 0.75, output: 4.50, used: false },
};

const TOTAL_INPUT = DATA.traditional.total_tasks * DATA.traditional.avg_input_tokens;
const TOTAL_OUTPUT_TRAD = DATA.traditional.total_tasks * DATA.traditional.avg_output_tokens;
const TOTAL_OUTPUT_ONT0 = DATA.ontoskills.total_tasks * DATA.ontoskills.avg_output_tokens;
const TOTAL_INPUT_ONT0 = DATA.ontoskills.total_tasks * DATA.ontoskills.avg_input_tokens;

function modelCost(m: ModelPrice, mode: 'traditional' | 'ontoskills'): number {
  const inp = mode === 'traditional' ? TOTAL_INPUT : TOTAL_INPUT_ONT0;
  const out = mode === 'traditional' ? TOTAL_OUTPUT_TRAD : TOTAL_OUTPUT_ONT0;
  return (inp * m.input + out * m.output) / 1_000_000;
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const TRAD = '#9763e1';  // --accent-purple
const ONTO = '#52c7e8';  // --accent-cyan
const PASS = '#85f496';  // --accent-mint
const PARTIAL = '#fbbf24';
const FAIL = '#6b7280';

function rewardCell(v: number) {
  if (v >= 1.0) return <span style={{ color: PASS, fontWeight: 700, fontSize: 13 }}>PASS</span>;
  if (v > 0) return <span style={{ color: PARTIAL, fontWeight: 700, fontSize: 13 }}>{(v * 100).toFixed(0)}%</span>;
  return <span style={{ color: FAIL, fontSize: 13 }}>—</span>;
}

/* ------------------------------------------------------------------ */
/* Section wrapper                                                     */
/* ------------------------------------------------------------------ */

function Section({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <div style={{
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: 24,
      marginBottom: 24,
      overflow: 'hidden',
      minWidth: 0,
    }}>
      <h3 style={{ marginTop: 0, marginBottom: note ? 4 : 16, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
        {title}
      </h3>
      {note && <p style={{ marginTop: 0, marginBottom: 16, fontSize: 12, color: 'var(--text-muted)' }}>{note}</p>}
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Per-task chart                                                      */
/* ------------------------------------------------------------------ */

function RewardChart() {
  const chartData = DATA.per_task.map(t => ({
    name: t.task_id.length > 16 ? t.task_id.slice(0, 14) + '…' : t.task_id,
    Traditional: t.traditional_reward,
    OntoSkills: t.ontoskills_reward,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} margin={{ top: 28, right: 12, bottom: 48, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
          stroke="rgba(255,255,255,0.06)"
          angle={-40}
          textAnchor="end"
          interval={0}
        />
        <YAxis
          domain={[0, 1]}
          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          stroke="rgba(255,255,255,0.06)"
          tickFormatter={v => `${(v * 100).toFixed(0)}%`}
          width={40}
        />
        <Tooltip
          formatter={(value: number, name: string) => [
            `${(value * 100).toFixed(0)}%`,
            name,
          ]}
          contentStyle={{
            background: '#1a1a1a',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 8,
            fontSize: 12,
            color: '#f5f5f5',
          }}
          itemStyle={{ color: '#f5f5f5' }}
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        <Bar dataKey="Traditional" fill={TRAD} radius={[3, 3, 0, 0]} maxBarSize={28}>
          <LabelList dataKey="Traditional" position="top" fontSize={10} fontWeight={600}
            fill="var(--text-muted)"
            formatter={(v: number) => v === 0 ? '' : `${(v * 100).toFixed(0)}%`}
          />
        </Bar>
        <Bar dataKey="OntoSkills" fill={ONTO} radius={[3, 3, 0, 0]} maxBarSize={28}>
          <LabelList dataKey="OntoSkills" position="top" fontSize={10} fontWeight={600}
            fill="var(--text-muted)"
            formatter={(v: number) => v === 0 ? '' : `${(v * 100).toFixed(0)}%`}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

export default function BenchmarkApp() {
  const t = DATA.traditional;
  const o = DATA.ontoskills;
  const deltaReward = o.avg_reward - t.avg_reward;
  const deltaCost = ((o.total_cost_usd - t.total_cost_usd) / t.total_cost_usd * 100);

  return (
    <div style={{ width: '100%', minWidth: 0 }}>

      {/* ── Headline metrics ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 28 }}>
        {[
          { label: 'Pass Rate', trad: `${(t.pass_rate * 100).toFixed(0)}%`, onto: `${(o.pass_rate * 100).toFixed(0)}%` },
          { label: 'Avg Reward', trad: t.avg_reward.toFixed(2), onto: o.avg_reward.toFixed(2) },
          { label: 'Tasks Passed', trad: `${t.tasks_passed}/${t.total_tasks}`, onto: `${o.tasks_passed}/${o.total_tasks}` },
          { label: 'Cost (GLM-5.1)', trad: `$${t.total_cost_usd.toFixed(2)}`, onto: `$${o.total_cost_usd.toFixed(2)}` },
        ].map(m => (
          <div key={m.label} style={{
            padding: '14px 16px', borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--bg-elevated)',
          }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>
              {m.label}
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontSize: 20, fontWeight: 700, color: TRAD, fontFamily: "'JetBrains Mono', monospace" }}>{m.trad}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>vs</span>
              <span style={{ fontSize: 20, fontWeight: 700, color: ONTO, fontFamily: "'JetBrains Mono', monospace" }}>{m.onto}</span>
            </div>
          </div>
        ))}
      </div>

      {/* ── Per-task chart ── */}
      <Section title="Per-Task Score" note="Score = tests passed / tests total. Evaluated via Docker + pytest (deterministic).">
        <RewardChart />
      </Section>

      {/* ── Cost comparison table ── */}
      <Section
        title="Estimated Cost by Model"
        note={`Token usage measured from glm-5.1 benchmark (${t.total_tasks} tasks, seed=7). Costs for other models are extrapolated from the same token counts — they did not run the benchmark.`}
      >
        <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 500 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--border)' }}>
              <th style={{ textAlign: 'left', padding: '8px 8px', fontWeight: 600 }}>Model</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11 }}>Input $/MTok</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11 }}>Output $/MTok</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600, color: TRAD }}>Traditional</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600, color: ONTO }}>OntoSkills</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600 }}>Savings</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(MODELS).map(([id, m]) => {
              const tradCost = modelCost(m, 'traditional');
              const ontoCost = modelCost(m, 'ontoskills');
              const savings = ((tradCost - ontoCost) / tradCost * 100);
              return (
                <tr key={id} style={{
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  background: m.used ? 'rgba(82,199,232,0.05)' : 'transparent',
                }}>
                  <td style={{ padding: '8px 8px', fontWeight: m.used ? 600 : 400 }}>
                    {m.label}
                    {m.used && <span style={{ fontSize: 9, marginLeft: 6, color: ONTO, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>actual</span>}
                  </td>
                  <td style={{ padding: '8px 8px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                    ${m.input.toFixed(2)}
                  </td>
                  <td style={{ padding: '8px 8px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                    ${m.output.toFixed(2)}
                  </td>
                  <td style={{ padding: '8px 8px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", color: TRAD }}>
                    ${tradCost.toFixed(2)}
                  </td>
                  <td style={{ padding: '8px 8px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", color: ONTO }}>
                    ${ontoCost.toFixed(2)}
                  </td>
                  <td style={{
                    padding: '8px 8px', textAlign: 'right', fontWeight: 600,
                    color: savings > 0 ? PASS : FAIL,
                    fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
                  }}>
                    {savings > 0 ? '-' : '+'}{Math.abs(savings).toFixed(0)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </Section>

      {/* ── Per-task detail table ── */}
      <Section title="Task Results">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--border)' }}>
              <th style={{ textAlign: 'left', padding: '8px 8px', fontWeight: 600 }}>Task</th>
              <th style={{ textAlign: 'center', padding: '8px 8px', fontWeight: 600, color: TRAD, minWidth: 80 }}>Traditional</th>
              <th style={{ textAlign: 'center', padding: '8px 8px', fontWeight: 600, color: ONTO, minWidth: 80 }}>OntoSkills</th>
              <th style={{ textAlign: 'center', padding: '8px 8px', fontWeight: 600, minWidth: 60 }}>Delta</th>
            </tr>
          </thead>
          <tbody>
            {DATA.per_task.map(t => {
              const delta = t.ontoskills_reward - t.traditional_reward;
              return (
                <tr key={t.task_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '8px 8px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                    {t.task_id}
                  </td>
                  <td style={{ textAlign: 'center', padding: '8px 8px' }}>{rewardCell(t.traditional_reward)}</td>
                  <td style={{ textAlign: 'center', padding: '8px 8px' }}>{rewardCell(t.ontoskills_reward)}</td>
                  <td style={{ textAlign: 'center', padding: '8px 8px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
                    color: delta > 0 ? PASS : delta < 0 ? '#f87171' : 'var(--text-muted)',
                    fontWeight: delta !== 0 ? 600 : 400,
                  }}>
                    {delta > 0 ? '+' : ''}{delta > 0 ? `${(delta * 100).toFixed(0)}%` : delta < 0 ? `${(delta * 100).toFixed(0)}%` : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Section>
    </div>
  );
}
