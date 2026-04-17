export const CATEGORY_COLORS: Record<string, string> = {
  skill:         '#52c7e8',
  main:          '#818cf8',
  prompt:        '#4ade80',
  test:          '#fbbf24',
  module:        '#f472b6',
  dependency:    '#fb923c',
  AntiPattern:   '#ef4444',
  RecoveryTactic:'#e879f9',
  failure:       '#a16207',
  yield:         '#2dd4bf',
  require:       '#a78bfa',
  tool:          '#facc15',
  productivity:  '#38bdf8',
  development:   '#67e8f9',
};

export const PALETTE_FALLBACK = ['#f97316','#ec4899','#06b6d4','#84cc16','#d946ef','#14b8a6','#f43f5e','#0ea5e9','#eab308','#7c3aed','#10b981','#e11d48','#6366f1','#f59e0b','#22d3ee','#be123c'];

export function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export function getNodeColor(category: string, isHighlighted: boolean): string {
  if (isHighlighted) return '#52c7e8';
  if (CATEGORY_COLORS[category]) return CATEGORY_COLORS[category];
  return PALETTE_FALLBACK[hashStr(category) % PALETTE_FALLBACK.length];
}

export function getConnectedNodes(node: import('../types').GraphNode, edges: import('../types').GraphEdge[], allNodes: import('../types').GraphNode[]): import('../types').GraphNode[] {
  const ids = new Set<string>();
  for (const e of edges) {
    if (e.source === node.id) ids.add(e.target);
    if (e.target === node.id) ids.add(e.source);
  }
  return allNodes.filter(n => ids.has(n.id));
}

export const CATEGORY_LABELS: Record<string, [string, string]> = {
  skill: ['Skill', CATEGORY_COLORS.skill],
  main: ['ontoskill.ttl', CATEGORY_COLORS.main],
  prompt: ['Prompt', CATEGORY_COLORS.prompt],
  test: ['Test', CATEGORY_COLORS.test],
  module: ['Module', CATEGORY_COLORS.module],
  dependency: ['Depends on', CATEGORY_COLORS.dependency],
  AntiPattern: ['Anti-pattern', CATEGORY_COLORS.AntiPattern],
  RecoveryTactic: ['Recovery', CATEGORY_COLORS.RecoveryTactic],
  failure: ['Failure', CATEGORY_COLORS.failure],
  yield: ['Yields', CATEGORY_COLORS.yield],
  require: ['Requires', CATEGORY_COLORS.require],
  tool: ['Tool', CATEGORY_COLORS.tool],
  productivity: ['Productivity', CATEGORY_COLORS.productivity],
  development: ['Development', CATEGORY_COLORS.development],
};

export const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  skill: 'The root skill definition',
  main: 'Primary ontology file',
  prompt: 'Prompt template definitions',
  test: 'Test specifications',
  module: 'Additional ontology modules',
  dependency: 'Required skill dependencies',
  AntiPattern: 'Common mistakes to avoid',
  RecoveryTactic: 'Error recovery strategies',
  failure: 'Known failure modes',
  yield: 'States produced after execution',
  require: 'States required before execution',
  tool: 'Allowed tool integrations',
};
