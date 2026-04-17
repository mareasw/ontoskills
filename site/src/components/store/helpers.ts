import type { Skill, GraphNode, GraphEdge } from './types';
import { OFFICIAL_STORE_INDEX_URL } from '../../data/store';

export const STORE_INDEX_URL = OFFICIAL_STORE_INDEX_URL;
export const TTL_BASE = STORE_INDEX_URL.replace('index.json', 'packages/');

export function normSkill(pkg: any, skill: any): Skill {
  const qid = `${pkg.package_id}/${skill.id}`;
  const parts = qid.split('/');
  return {
    packageId: pkg.package_id,
    skillId: skill.id,
    qualifiedId: qid,
    description: skill.description || pkg.description || '',
    aliases: Array.isArray(skill.aliases) ? skill.aliases : [],
    trustTier: pkg.trust_tier || 'verified',
    installCommand: `npx ontoskills install ${qid}`,
    author: parts[0] || '',
    category: skill.category || '',
    intents: Array.isArray(skill.intents) ? skill.intents : [],
    dependsOn: Array.isArray(skill.depends_on_skills) ? skill.depends_on_skills : [],
    version: pkg.version || '',
    modules: Array.isArray(pkg.modules) ? pkg.modules : [],
  };
}

export function buildGraphData(skillList: Skill[], highlightId: string | null = null) {
  const idSet = new Set(skillList.map(s => s.skillId));
  const nodes: GraphNode[] = skillList.map(s => ({
    id: s.skillId,
    label: s.skillId,
    category: s.category,
    qualifiedId: s.qualifiedId,
    isHighlighted: s.skillId === highlightId,
  }));
  const edges: GraphEdge[] = [];
  for (const s of skillList) {
    for (const d of s.dependsOn) {
      if (d !== s.skillId && idSet.has(d)) edges.push({ source: s.skillId, target: d });
    }
  }
  return { nodes, edges };
}

export function packageHasDeps(skillList: Skill[]) {
  const idSet = new Set(skillList.map(s => s.skillId));
  return skillList.some(s => s.dependsOn.some(d => idSet.has(d)));
}

export function navClick(href: string, navigate: (href: string) => void) {
  return (e: React.MouseEvent) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(href);
  };
}

export function buildFileGraphData(modules: string[], skillId: string) {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const mainFile = `${skillId}/ontoskill.ttl`;
  const skillModules = modules.filter(m => m.startsWith(skillId + '/'));

  for (const m of skillModules) {
    const fileName = m.split('/').pop() || m;
    const isMain = m === mainFile;
    nodes.push({
      id: m,
      label: fileName,
      category: isMain ? 'main' : fileName.includes('test') ? 'test' : fileName.includes('prompt') ? 'prompt' : 'module',
      qualifiedId: m,
      isHighlighted: isMain,
    });
    if (!isMain && skillModules.includes(mainFile)) {
      edges.push({ source: mainFile, target: m });
    }
  }
  return { nodes, edges };
}

export function parseTtlKnowledgeMap(ttlContent: string, skillId: string) {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const rootId = `skill:${skillId}`;
  const seen = new Set<string>();

  nodes.push({ id: rootId, label: skillId, category: 'skill', qualifiedId: skillId, isHighlighted: true });
  seen.add(rootId);

  const addNode = (id: string, label: string, category: string): GraphNode | null => {
    if (seen.has(id)) return null;
    seen.add(id);
    const node: GraphNode = { id, label, category, qualifiedId: id, isHighlighted: false };
    nodes.push(node);
    return node;
  };

  for (const m of ttlContent.matchAll(/oc:dependsOnSkill\s+oc:skill_([^\s;,]+)/g)) {
    const depId = `dep:${m[1]}`;
    addNode(depId, m[1].replace(/_/g, '-'), 'dependency');
    edges.push({ source: rootId, target: depId });
  }

  const knRefs = new Set<string>();
  for (const m of ttlContent.matchAll(/oc:(kn_[a-f0-9]+)/g)) {
    knRefs.add(m[1]);
  }
  for (const knId of knRefs) {
    const typeMatch = ttlContent.match(new RegExp(`oc:${knId}\\s+a\\s+oc:KnowledgeNode(?:,\\s*oc:(\\w+))?`));
    if (!typeMatch) continue;
    const knType = typeMatch[1] || 'KnowledgeNode';
    const ctxMatch = ttlContent.match(new RegExp(`oc:${knId}[\\s\\S]*?oc:appliesToContext\\s+"([^"]+)"`));
    const fullContext = ctxMatch ? ctxMatch[1] : '';
    const label = fullContext.length > 40 ? fullContext.slice(0, 40) + '…' : fullContext || knType.replace(/([A-Z])/g, ' $1').trim();
    const condMatch = ttlContent.match(new RegExp(`oc:${knId}[\\s\\S]*?oc:appliesToCondition\\s+"([^"]+)"`));
    const description = [fullContext, condMatch?.[1]].filter(Boolean).join(' — ') || undefined;
    const knNode = addNode(knId, label, knType);
    if (knNode) knNode.description = description;
    edges.push({ source: rootId, target: knId });
  }

  for (const m of ttlContent.matchAll(/oc:(yieldsState|requiresState)\s+oc:(\w+)/g)) {
    const stateId = `state:${m[2]}`;
    const stateLabel = m[2].replace(/([A-Z])/g, ' $1').trim();
    const stateNode = addNode(stateId, stateLabel, m[1] === 'yieldsState' ? 'yield' : 'require');
    if (stateNode) stateNode.description = m[1] === 'yieldsState' ? `Produced after ${stateLabel.toLowerCase()}` : `Required before execution`;
    edges.push({ source: rootId, target: stateId });
  }
  for (const m of ttlContent.matchAll(/^\s+oc:(\w+)\s*[,;]$/gm)) {
    const name = m[1];
    if (/^[A-Z]/.test(name)) {
      const stateId = `state:${name}`;
      if (!seen.has(stateId)) {
        addNode(stateId, name.replace(/([A-Z])/g, ' $1').trim(), 'yield');
        edges.push({ source: rootId, target: stateId });
      }
    }
  }

  for (const m of ttlContent.matchAll(/oc:handlesFailure\s+oc:(\w+)/g)) {
    const failId = `fail:${m[1]}`;
    addNode(failId, m[1].replace(/([A-Z])/g, ' $1').trim(), 'failure');
    edges.push({ source: rootId, target: failId });
  }

  for (const m of ttlContent.matchAll(/oc:hasAllowedTool\s+"(\w+)"/g)) {
    const toolId = `tool:${m[1]}`;
    addNode(toolId, m[1], 'tool');
    edges.push({ source: rootId, target: toolId });
  }

  return { nodes, edges };
}
