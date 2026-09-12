import { useLayoutEffect, useRef, type DependencyList } from 'react';

export interface RequestScope { active: boolean; controller: AbortController; }

export function useRequestScope(dependencies: DependencyList) {
  const ref = useRef<RequestScope>({ active: false, controller: new AbortController() });
  useLayoutEffect(() => {
    const current = { active: true, controller: new AbortController() };
    ref.current = current;
    return () => { current.active = false; current.controller.abort(); };
  }, dependencies);
  return ref;
}