// Geometry and layout only. Never changes native identities, links or assertions.
export function hash(text) {
  let value = 2166136261;
  for (const char of String(text)) value = Math.imul(value ^ char.charCodeAt(0), 16777619);
  return value >>> 0;
}

export function radius(node, zoom = 1) {
  return (5 + Math.min(Math.sqrt(Math.max(0, node.degree || 0)), 7) * 1.35)
    * Math.max(.65, Math.min(1.6, Math.sqrt(zoom)));
}

export function initialise(nodes) {
  const groups = new Map();
  for (const n of [...nodes].sort((a,b) => String(a.id).localeCompare(String(b.id)))) {
    const key = n.community ?? 'unassigned';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(n);
  }
  const ordered = [...groups.entries()].sort((a,b) => b[1].length-a[1].length || String(a[0]).localeCompare(String(b[0])));
  const packed=[];
  ordered.forEach(([key, members], group) => {
    const clusterRadius=Math.sqrt(members.length)*34+50;
    let cx=0,cy=0;
    // Pack differently sized groups without starting them on top of each other.
    // This is spatial organisation only; membership comes from native metadata.
    for(let attempt=0;group&&attempt<5000;attempt++){
      const angle=attempt*2.39996323,distance=Math.sqrt(attempt)*39;
      cx=Math.cos(angle)*distance;cy=Math.sin(angle)*distance;
      if(packed.every(p=>Math.hypot(cx-p.x,cy-p.y)>clusterRadius+p.r+40))break;
    }
    packed.push({x:cx,y:cy,r:clusterRadius});
    members.sort((a,b) => (b.degree||0)-(a.degree||0) || String(a.id).localeCompare(String(b.id)));
    members.forEach((n,i) => {
      const theta = i * 2.39996323 + (hash(key)%100) / 100;
      n.x = cx + Math.cos(theta) * Math.sqrt(i) * 43;
      n.y = cy + Math.sin(theta) * Math.sqrt(i) * 43;
      // Preserve breathing room inside a community instead of attracting every
      // member to exactly the same point. Edges and repulsion can still settle.
      n.cx = n.x; n.cy = n.y;
      n.vx = n.vy = 0;
    });
  });
}

export function stepLayout(nodes, edges, lookup, cooling = 1) {
  for (let i=0;i<nodes.length;i++) {
    const a=nodes[i];
    a.vx += (a.cx-a.x)*.008; a.vy += (a.cy-a.y)*.008;
    for (let j=i+1;j<nodes.length;j++) {
      const b=nodes[j];
      let dx=a.x-b.x,dy=a.y-b.y;
      if (Math.abs(dx)+Math.abs(dy)<.001) {dx=.1;dy=.1;}
      const d=Math.hypot(dx,dy), gap=34+Math.min(Math.sqrt((a.degree||0)+(b.degree||0)),12);
      const force=Math.min(5,110/Math.max(d*d,1) + Math.max(0,gap-d)*.045)*cooling;
      const fx=dx/d*force,fy=dy/d*force;
      a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;
    }
  }
  for (const e of edges) {
    const a=lookup.get(e.source), b=lookup.get(e.target);
    if (!a || !b || a===b) continue;
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;
    const same=a.community===b.community,target=same?83:300,f=(d-target)*(same?.0015:.0008)*cooling;
    const sa=1/Math.sqrt(Math.max(1,a.degree||1)),sb=1/Math.sqrt(Math.max(1,b.degree||1));
    a.vx+=dx/d*f*sa;a.vy+=dy/d*f*sa;b.vx-=dx/d*f*sb;b.vy-=dy/d*f*sb;
  }
  for (const n of nodes) {
    n.vx*=.65;n.vy*=.65;
    if (!n.pinned) {n.x+=Math.max(-7,Math.min(7,n.vx));n.y+=Math.max(-7,Math.min(7,n.vy));}
  }
}

export function fitCamera(nodes, bounds) {
  if (!nodes.length) return {x:0,y:0,k:1};
  const xs=nodes.map(n=>n.x),ys=nodes.map(n=>n.y);
  const left=Math.min(...xs)-40,right=Math.max(...xs)+40,top=Math.min(...ys)-40,bottom=Math.max(...ys)+40;
  const k=Math.max(.04,Math.min(2.2,bounds.width/Math.max(right-left,100),bounds.height/Math.max(bottom-top,100)));
  return {k,x:bounds.x+bounds.width/2-(left+right)/2*k,y:bounds.y+bounds.height/2-(top+bottom)/2*k};
}

export function curve(a,b,id) {
  if (Math.hypot(a.x-b.x,a.y-b.y)<.001) {
    return {a:{x:a.x-2,y:a.y},b:{x:b.x+2,y:b.y},c:{x:a.x,y:a.y-60}};
  }
  const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy),bend=Math.min(32,d*.065)*(hash(id)%2?1:-1);
  return {a,b,c:{x:(a.x+b.x)/2-dy/d*bend,y:(a.y+b.y)/2+dx/d*bend}};
}

export function curvePoint(g,t) {
  return {x:(1-t)**2*g.a.x+2*(1-t)*t*g.c.x+t*t*g.b.x,
          y:(1-t)**2*g.a.y+2*(1-t)*t*g.c.y+t*t*g.b.y};
}

export function curveDistance(g,p) {
  let best=Infinity, a=g.a;
  for (let i=1;i<=20;i++) {
    const b=curvePoint(g,i/20),dx=b.x-a.x,dy=b.y-a.y;
    const t=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy||1)));
    best=Math.min(best,Math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy));a=b;
  }
  return best;
}

export function assertionDirections(edge,lookup) {
  const normal=s=>String(s||'').replaceAll('_',' ').replace(/\s+/g,' ').trim().toUpperCase();
  const source=normal(lookup.get(edge.source)?.label),target=normal(lookup.get(edge.target)?.label),found=new Set();
  if (!source || !target || source===target) return [];
  for (const claim of edge.assertion_evidence||[]) {
    const a=normal(claim.source),b=normal(claim.target);
    if (a===source && b===target) found.add(1);
    if (a===target && b===source) found.add(-1);
  }
  return [...found];
}

export function graphCounts(nodes,edges,visible) {
  return {nodes:nodes.filter(n=>visible.has(n.id)).length,
          edges:edges.filter(e=>visible.has(e.source)&&visible.has(e.target)).length};
}

export function citedRecords(answer,evidence) {
  const nodes=new Set(),edges=new Set();
  for(const block of String(answer||'').matchAll(/\[Data:([^\]]+)\]/g)) {
    for(const ref of block[1].matchAll(/([A-Za-z ]+)\s*\(([^)]+)\)/g)) {
      const category=ref[1].trim().toLowerCase();
      if(!['entities','relationships'].includes(category))continue;
      const ids=new Set(ref[2].match(/\b\d+\b/g)||[]);
      for(const row of evidence?.[category]||[])if(ids.has(String(row.citation_id)))
        (category==='entities'?nodes:edges).add(row.native_id);
    }
  }
  return {nodes:[...nodes],edges:[...edges]};
}
