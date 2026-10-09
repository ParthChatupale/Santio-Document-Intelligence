export function Icon({name, size = 20}: {name: string; size?: number}) {
  const paths: Record<string, React.ReactNode> = {
    library: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
    back: <path d="M20 12H4m6-6-6 6 6 6"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    review: <><path d="M12 8v5m0 3v.1"/><path d="m12 3 10 18H2L12 3Z"/></>,
    compare: <><path d="M5 20V9m7 11V3m7 17v-7"/><path d="M3 20h18"/></>,
    source: <><path d="M6 3h9l4 4v14H6V3Zm9 0v5h4M9 12h7m-7 4h7"/></>,
    export: <><path d="M12 3v13m-5-5 5 5 5-5M4 18v3h16v-3"/></>,
    layers: <><path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5"/></>,
    pause: <><path d="M8 5v14m8-14v14"/></>,
    play: <path d="m8 4 12 8-12 8V4Z"/>,
    zoom: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6m-3-3v6"/></>,
    chevron: <path d="m9 5 7 7-7 7"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.source}</svg>;
}
