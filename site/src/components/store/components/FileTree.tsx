import { useMemo, useState } from 'react';
import { OFFICIAL_STORE_REPO_URL } from '../../../data/store';

export function FileTree({ modules, pkgId }: { modules: string[]; pkgId?: string }) {
  const tree = useMemo(() => {
    const root: any = {};
    for (const m of modules) {
      const parts = m.split('/');
      let node = root;
      for (let i = 0; i < parts.length; i++) {
        const p = parts[i];
        if (i === parts.length - 1) { node[p] = node[p] || { __file: true }; }
        else { node[p] = node[p] || {}; node = node[p]; }
      }
    }
    return root;
  }, [modules]);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const fileUrl = (filePath: string) =>
    pkgId ? `${OFFICIAL_STORE_REPO_URL}/blob/main/packages/${pkgId}/${filePath}` : undefined;

  const renderNode = (node: any, path: string = '', depth: number = 0): JSX.Element[] => {
    const entries = Object.entries(node).sort(([aName, a]: [string, any], [bName, b]: [string, any]) => {
      const aDir = !a.__file, bDir = !b.__file;
      if (aDir !== bDir) return aDir ? -1 : 1;
      return aName.localeCompare(bName);
    });
    const elements: JSX.Element[] = [];
    for (const [name, val] of entries) {
      const fullPath = path ? `${path}/${name}` : name;
      if ((val as any).__file) {
        const isOnto = name === 'ontoskill.ttl';
        const href = fileUrl(fullPath);
        const Wrapper = href ? 'a' : 'div';
        const wrapperProps = href ? { href, target: '_blank', rel: 'noopener noreferrer' } : {};
        elements.push(
          <Wrapper key={fullPath} {...(wrapperProps as any)} className={`flex items-center gap-2 py-0.5 group/file ${href ? 'cursor-pointer' : ''}`} style={{ paddingLeft: `${depth * 1.25}rem` }}>
            <svg className="w-3.5 h-3.5 shrink-0 text-[#8a8a8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            <span className={`font-mono text-xs ${isOnto ? 'text-[#52c7e8]' : 'text-[#8a8a8a]'} ${href ? 'group-hover/file:text-[#52c7e8] transition-colors' : ''}`}>{name}</span>
            {href && <svg className="w-3 h-3 text-[#555] group-hover/file:text-[#52c7e8] transition-colors shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>}
          </Wrapper>
        );
      } else {
        const isExpanded = expanded.has(fullPath);
        elements.push(
          <div key={fullPath}>
            <div
              className="flex items-center gap-1.5 py-0.5 cursor-pointer hover:text-[#52c7e8] select-none"
              style={{ paddingLeft: `${depth * 1.25}rem` }}
              onClick={() => setExpanded(prev => { const next = new Set(prev); next.has(fullPath) ? next.delete(fullPath) : next.add(fullPath); return next; })}
            >
              <svg className={`w-3.5 h-3.5 shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>
              <span className="font-mono text-xs">{name}/</span>
            </div>
            {isExpanded && renderNode(val, fullPath, depth + 1)}
          </div>
        );
      }
    }
    return elements;
  };

  return <div className="text-[#d4d4d4]">{renderNode(tree)}</div>;
}
