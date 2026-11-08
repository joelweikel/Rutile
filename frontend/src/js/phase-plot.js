// Vector boundaries over a display raster. Pixel count never changes solver resolution.
const NS = 'http://www.w3.org/2000/svg';
const $ = id => document.getElementById(id);
const palette = ['#29d9ed', '#ff6f59', '#b790ff', '#ffd24c', '#42e69b', '#ff70be', '#538fff', '#b8e54b', '#ff9e42', '#48ded0', '#df85fa', '#f3df93', '#d8edff'];
const plot = {left:76, top:25, width:670, height:465};
const fmt = (v,d=1) => Number.isFinite(v) ? v.toLocaleString(undefined,{maximumFractionDigits:d}) : 'Unavailable';
const symbol = value => value[0]+value.slice(1).toLowerCase();
const key = phases => phases?.map(p=>p.label).sort().join(' + ') || 'Unresolved';
function svg(tag, attrs={}, text='') {const n=document.createElementNS(NS,tag); for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v); n.textContent=text; return n;}
function el(tag, cls='', text='') {const n=document.createElement(tag); n.className=cls; n.textContent=text; return n;}

export function sectionsAt(boundaries, t) {
  const sections=[];
  for(const r of boundaries?.ribbons || []) for(let i=1;i<r.ties.length;i++) {
    const a=r.ties[i-1],b=r.ties[i],dt=b.temperature-a.temperature,w=(t-a.temperature)/dt;
    if(Math.abs(dt)<1e-9 || w < -1e-9 || w > 1+1e-9 || a.phases.join('|')!==b.phases.join('|'))continue;
    sections.push({left:a.left+w*(b.left-a.left),right:a.right+w*(b.right-a.right),phases:a.phases});
  }
  for(const b of boundaries?.single_phase_bands||[])if(t>=b.temperature_min&&t<=b.temperature_max)sections.push({left:0,right:1,phases:[b.phase]});
  return sections;
}

export function predict(sections, x, components) {
  const inside=sections.filter(s=>x>=s.left&&x<=s.right);
  let parts;
  if(inside.length) {
    if(new Set(inside.map(s=>s.phases.join('|'))).size!==1)return null;
    const s=inside.reduce((a,b)=>a.right-a.left < b.right-b.left ? a:b),f=(x-s.left)/(s.right-s.left);
    if(s.phases.length===1) {
      const p=s.phases[0];
      return [{phase:p,label:p,fraction:1,composition:{[components[0]]:1-x,[components[1]]:x}}];
    }
    parts=s.phases.map((p,i)=>({phase:p,label:p,fraction:i?f:1-f,composition:{[components[0]]:1-(i?s.right:s.left),[components[1]]:i?s.right:s.left}}));
    if(parts[0].phase===parts[1].phase)parts.forEach((p,i)=>p.label+=` #${i+1}`);
  } else {
    const left=sections.filter(s=>s.right<x).sort((a,b)=>b.right-a.right)[0],right=sections.filter(s=>s.left>x).sort((a,b)=>a.left-b.left)[0];
    const names=[left?.phases[1],right?.phases[0]].filter(Boolean);
    if(!names.length||new Set(names).size!==1)return null;
    parts=[{phase:names[0],label:names[0],fraction:1,composition:{[components[0]]:1-x,[components[1]]:x}}];
  }
  return parts;
}

export function createPhasePlot() {
  let data=null, complete=false, colors=new Map(), pinned=false, selection=null, samples=new Map(), colorIndex=0;
  let activePhases=new Set();
  const labelPositions=new Map();
  let labelDrag=null, suppressLabelClick=false;
  const rgb=c=>c.match(/\w\w/g).map(h=>parseInt(h,16));
  const color=p=>colors.get(p)||'#8796aa';
  function phaseRGB(phases) {
    const mixed=[0,0,0];
    for(const p of phases) {const c=rgb(color(p.phase).slice(1)); c.forEach((v,i)=>mixed[i]+=v*p.fraction);}
    // A split phase retains its base color; composition contrast is shown with
    // a lightness shift and explicit #1/#2 labels, not a fictitious phase color.
    if(phases.length===2&&phases[0].phase===phases[1].phase) {
      const f=phases[1].fraction;
      return mixed.map(v=>v*(0.6+0.4*f));
    }
    return mixed;
  }
  const px=x=>plot.left+x*plot.width;
  const py=t=>plot.top+plot.height-(t-data.settings.temperature_min)/(data.settings.temperature_max-data.settings.temperature_min)*plot.height;
  function sampleAt(x,t) {
    const s=data.settings,xi=Math.max(0,Math.min(s.composition_points-1,Math.floor(x*s.composition_points))),ti=Math.max(0,Math.min(s.temperature_points-1,Math.floor((t-s.temperature_min)/(s.temperature_max-s.temperature_min)*s.temperature_points)));
    return samples.get(`${xi},${ti}`);
  }
  function at(x,t,sections=sectionsAt(data.boundaries,t)) {
    const sample=sampleAt(x,t), prediction=predict(sections,x,data.settings.components);
    // Failed independent equilibria remain gaps even if a map prediction exists.
    if(sample&&!sample.valid)return {phases:null,sample,prediction,source:'Unresolved equilibrium sample'};
    return {phases:prediction||sample?.phases,sample,prediction,source:prediction?'Boundary interpolation + lever rule':'Nearest independent sample'};
  }
  function axes() {
    const root=$('plot'); root.replaceChildren(); root.setAttribute('viewBox','0 0 780 580');
    const defs=svg('defs');
    const clip=svg('clipPath',{id:'plot-clip'});clip.append(svg('rect',{x:plot.left,y:plot.top,width:plot.width,height:plot.height}));defs.append(clip);
    const arrow=svg('marker',{id:'label-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});arrow.append(svg('path',{d:'M0 0L10 5L0 10Z',fill:'#f4f7ff'}));defs.append(arrow);root.append(defs);
    root.append(svg('rect',{x:plot.left,y:plot.top,width:plot.width,height:plot.height,fill:'#0a101a',stroke:'#617085'}));
    root.append(svg('g',{id:'fills','clip-path':'url(#plot-clip)'}));
    for(let i=0;i<=5;i++) {
      const x=px(i/5),y=plot.top+i/5*plot.height,t=data.settings.temperature_max-i/5*(data.settings.temperature_max-data.settings.temperature_min);
      root.append(svg('line',{x1:x,x2:x,y1:plot.top,y2:plot.top+plot.height,stroke:'#fff',opacity:.12}),svg('line',{x1:plot.left,x2:plot.left+plot.width,y1:y,y2:y,stroke:'#fff',opacity:.12}));
      root.append(svg('text',{x,y:515,'text-anchor':'middle',fill:'#c6cfdb','font-size':13},String(i*20)),svg('text',{x:plot.left-12,y:y+4,'text-anchor':'end',fill:'#c6cfdb','font-size':13},fmt(t,0)));
    }
    root.append(svg('text',{x:411,y:548,'text-anchor':'middle',fill:'#e1e8f3','font-size':14},`${symbol(data.settings.components[1])} composition / atomic %`),svg('text',{x:20,y:257,transform:'rotate(-90 20 257)','text-anchor':'middle',fill:'#e1e8f3','font-size':14},'Temperature / K'));
    root.append(svg('g',{id:'boundaries','clip-path':'url(#plot-clip)','pointer-events':'none'}),svg('g',{id:'checks','clip-path':'url(#plot-clip)','pointer-events':'none'}),svg('g',{id:'region-labels'}));
    root.append(svg('circle',{id:'selection',r:5,fill:'#101722',stroke:'#fff','stroke-width':2,visibility:'hidden','pointer-events':'none'}));
  }
  function fills() {
    const width=1005,height=698,canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
    const ctx=canvas.getContext('2d'),image=ctx.createImageData(width,height),s=data.settings;
    for(let y=0;y<height;y++) {
      const t=s.temperature_max-(y+.5)/height*(s.temperature_max-s.temperature_min),sections=sectionsAt(data.boundaries,t);
      // Build constant topology spans once per row, then color continuously.
      const cuts=[...new Set([0,1,...sections.flatMap(r=>[r.left,r.right])])].filter(x=>x>=0&&x<=1).sort((a,b)=>a-b);
      const spans=cuts.slice(1).map((right,i)=>({left:cuts[i],right,phases:predict(sections,(cuts[i]+right)/2,s.components)}));
      let span=0;
      for(let x=0;x<width;x++) {
        const composition=(x+.5)/width;
        while(span<spans.length-1&&composition>spans[span].right)span++;
        const sample=sampleAt(composition,t);let phases=spans[span]?.phases;
        if(phases?.length===2) {
          const a=phases[0].composition[s.components[1]],b=phases[1].composition[s.components[1]],f=(composition-a)/(b-a);
          phases=phases.map((p,i)=>({...p,fraction:i?f:1-f}));
        }
        if(!phases)phases=sample?.phases;
        const valid=phases?.length&&(!sample||sample.valid),offset=4*(y*width+x);
        let c=valid?phaseRGB(phases):((x+y)%12<3?[59,71,89]:[13,21,33]);
        if(valid&&!spans[span]?.phases&&(x+y)%16<2)c=c.map(v=>v*.7); // sampled-only coverage
        image.data.set([...c.map(v=>Math.max(0,Math.min(255,Math.round(v)))),255],offset);
      }
    }
    ctx.putImageData(image,0,0);
    $('fills').append(svg('image',{x:plot.left,y:plot.top,width:plot.width,height:plot.height,href:canvas.toDataURL()}));
  }
  function boundaries() {
    for(const r of data.boundaries?.ribbons||[]) for(const side of ['left','right']) {
      const d=r.ties.map((p,i)=>`${i?'L':'M'}${px(p[side])},${py(p.temperature)}`).join(' ');
      $('boundaries').append(svg('path',{d,fill:'none',stroke:'#101622','stroke-width':3.6,'stroke-linejoin':'round'}),svg('path',{d,fill:'none',stroke:'#f6f8ff','stroke-width':1.25,'stroke-linejoin':'round'}));
    }
    for(const n of data.boundaries?.invariants||[])$('boundaries').append(svg('path',{d:`M${px(Math.min(...n.compositions))},${py(n.temperature)}H${px(Math.max(...n.compositions))}`,stroke:'#fff','stroke-width':1.5,'stroke-dasharray':n.approximate?'4 3':'none'}));
  }
  function markers() {
    $('checks').replaceChildren();
    for(const c of data.cells||[]) {
      if(c.check!=='disagreement'&&!$('show-samples').checked)continue;
      const x=px((c.xi+.5)/data.settings.composition_points),y=py(data.settings.temperature_min+(c.ti+.5)/data.settings.temperature_points*(data.settings.temperature_max-data.settings.temperature_min));
      if(c.check==='disagreement')$('checks').append(svg('path',{d:`M${x-3},${y-3}l6,6m-6,0l6,-6`,stroke:'#ff295e','stroke-width':1.7}));
      else $('checks').append(svg('circle',{cx:x,cy:y,r:1.5,fill:c.check==='agreement'?'#ffffffb0':'#8793a6'}));
    }
  }
  function labels() {
    const nx=134,nt=93,regions=new Map(),seen=new Set(),lattice=[];
    for(let ti=0;ti<nt;ti++) {
      const t=data.settings.temperature_min+(ti+.5)/nt*(data.settings.temperature_max-data.settings.temperature_min),sections=sectionsAt(data.boundaries,t);
      for(let xi=0;xi<nx;xi++) {const value=at((xi+.5)/nx,t,sections);lattice.push(value.phases?.length?key(value.phases):'');}
    }
    for(let i=0;i<lattice.length;i++) {
      if(seen.has(i)||!lattice[i])continue;
      const name=lattice[i],queue=[i],indices=[];seen.add(i);
      for(let k=0;k<queue.length;k++) {const j=queue[k],x=j%nx,y=Math.floor(j/nx);indices.push(j);for(const [xx,yy]of [[x-1,y],[x+1,y],[x,y-1],[x,y+1]]) {const n=yy*nx+xx;if(xx>=0&&xx<nx&&yy>=0&&yy<nt&&!seen.has(n)&&lattice[n]===name){seen.add(n);queue.push(n);}}}
      if((regions.get(name)?.indices.length||0)<indices.length)regions.set(name,{indices,name});
    }
    const placed=[],callouts=[],covered=new Set();
    const measure=document.createElement('canvas').getContext('2d');measure.font='12px Estedad, sans-serif';
    function box(name,x,y) {const lines=name.split(' + '),width=Math.ceil(Math.max(...lines.map(line=>measure.measureText(line).width)))+18,height=lines.length*16+8;return {name,x,y,width,height,lines};}
    const overlaps=b=>placed.some(p=>Math.abs(p.x-b.x)<(p.width+b.width)/2+4&&Math.abs(p.y-b.y)<(p.height+b.height)/2+4);
    for(const region of [...regions.values()].sort((a,b)=>b.indices.length-a.indices.length)) {
      // Prefer a point with room on each side, rather than the centroid of a crescent.
      const candidates=region.indices.map(i=>{const xi=i%nx,ti=Math.floor(i/nx);let distance=0;while(distance<20&&xi-distance>=0&&xi+distance<nx&&ti-distance>=0&&ti+distance<nt&&[i-distance,i+distance,i-distance*nx,i+distance*nx].every(j=>lattice[j]===region.name))distance++;return {i,distance};}).sort((a,b)=>b.distance-a.distance);
      let anchor=candidates[0],chosen;
      for(const c of candidates.slice(0,80)) {const b=box(region.name,px((c.i%nx+.5)/nx),plot.top+plot.height-(Math.floor(c.i/nx)+.5)/nt*plot.height);if(c.distance*5>=b.width/2&&c.distance*5>=b.height/2&&!overlaps(b)){chosen=b;anchor=c;break;}}
      const x=px((anchor.i%nx+.5)/nx),y=plot.top+plot.height-(Math.floor(anchor.i/nx)+.5)/nt*plot.height;
      if(chosen) {
        placed.push(chosen);
        region.name.split(' + ').forEach(p=>covered.add(p.split(' #')[0]));
      } else if(!region.name.includes(' + ')) {
        callouts.push({name:region.name,x,y});covered.add(region.name.split(' #')[0]);
      }
    }
    // Include narrow/stoichiometric phases absent from the label lattice.
    for(const p of activePhases)if(!covered.has(p)) {
      let point;
      for(const r of data.boundaries?.ribbons||[]) {const tie=r.ties[Math.floor(r.ties.length/2)],i=tie.phases.indexOf(p);if(i>=0){point={name:p,x:px(i?tie.right:tie.left),y:py(tie.temperature)};break;}}
      if(point)callouts.push(point);
    }
    function fits(b, name) {
      const left=Math.floor((b.x-b.width/2-5-plot.left)/plot.width*nx),right=Math.ceil((b.x+b.width/2+5-plot.left)/plot.width*nx);
      const bottom=Math.floor((plot.top+plot.height-b.y-b.height/2-5)/plot.height*nt),top=Math.ceil((plot.top+plot.height-b.y+b.height/2+5)/plot.height*nt);
      if(left<0||right>=nx||bottom<0||top>=nt)return false;
      for(let y=bottom;y<=top;y++)for(let x=left;x<=right;x++)if(lattice[y*nx+x]!==name)return false;
      return true;
    }
    const liquid=lattice.flatMap((name,i)=>name==='LIQUID'?[i]:[]);
    const external=[];
    for(const c of callouts) {
      // Use verified display cells in pure liquid as open label space. The arrow
      // still ends at the original phase anchor; no boundaries or data are moved.
      const slots=liquid.filter((_,i)=>i%2===0).map(i=>box(c.name,px((i%nx+.5)/nx),plot.top+plot.height-(Math.floor(i/nx)+.5)/nt*plot.height))
        .sort((a,b)=>Math.hypot(a.x-c.x,a.y-c.y)-Math.hypot(b.x-c.x,b.y-c.y));
      const chosen=slots.find(b=>!overlaps(b)&&fits(b,'LIQUID'));
      if(chosen) {chosen.anchor={x:c.x,y:c.y};chosen.placement='liquid';placed.push(chosen);}
      else external.push(c);
    }
    external.sort((a,b)=>a.y-b.y);
    let lastY=plot.top-28;
    external.forEach(c=>{c.labelY=Math.max(lastY+28,c.y);lastY=c.labelY;});
    let nextY=plot.top+plot.height+28;
    for(let i=external.length-1;i>=0;i--){external[i].labelY=Math.min(external[i].labelY,nextY-28);nextY=external[i].labelY;}
    for(const c of external) {const b=box(c.name,843,c.labelY);b.anchor={x:c.x,y:c.y};b.placement='margin';placed.push(b);}
    $('plot').setAttribute('viewBox',`0 0 ${external.length?940:780} ${Math.max(580,...placed.map(b=>b.y+b.height/2+12))}`);
    const svgPoint=event=>{const p=$('plot').createSVGPoint();p.x=event.clientX;p.y=event.clientY;return p.matrixTransform($('plot').getScreenCTM().inverse());};
    for(const b of placed) {
      b.anchor??={x:b.x,y:b.y};b.placement??='field';
      const saved=labelPositions.get(b.name);if(saved){b.x=saved.x;b.y=saved.y;b.placement='manual';}
      const group=svg('g',{'data-region-label':b.name,'data-label-placement':b.placement,tabindex:0,role:'button','aria-label':`Move ${b.name} label. Drag or use arrow keys; Shift moves farther.`,class:'phase-region-label'});
      const leader=svg('path',{fill:'none',stroke:'#f4f7ff','stroke-width':1,'marker-end':'url(#label-arrow)','pointer-events':'none'});
      const rect=svg('rect',{width:b.width,height:b.height,rx:5,fill:'#0b121ef2',stroke:'#ffffff70'});
      const text=b.lines.map(line=>svg('text',{'text-anchor':'middle',fill:'#f6f8ff','font-size':12},line));
      function position() {
        group.dataset.labelX=b.x;group.dataset.labelY=b.y;
        rect.setAttribute('x',b.x-b.width/2);rect.setAttribute('y',b.y-b.height/2);
        text.forEach((node,i)=>{node.setAttribute('x',b.x);node.setAttribute('y',b.y-(b.lines.length-1)*8+i*16+4);});
        const dx=b.anchor.x-b.x,dy=b.anchor.y-b.y;
        const edge=Math.min(1,(b.width/2+3)/(Math.abs(dx)||1e-9),(b.height/2+3)/(Math.abs(dy)||1e-9));
        leader.setAttribute('d',`M${b.x+dx*edge},${b.y+dy*edge}L${b.anchor.x},${b.anchor.y}`);
        leader.hidden=Math.abs(dx)<b.width/2&&Math.abs(dy)<b.height/2;
        leader.style.display=leader.hidden?'none':'';
      }
      function move(x,y) {
        const height=$('plot').viewBox.baseVal.height;
        b.x=Math.max(b.width/2+3,Math.min($('plot').viewBox.baseVal.width-3-b.width/2,x));b.y=Math.max(b.height/2+3,Math.min(height-b.height/2-3,y));
        labelPositions.set(b.name,{x:b.x,y:b.y});group.dataset.labelPlacement='manual';position();
      }
      group.append(leader,rect,...text);position();$('region-labels').append(group);
      group.addEventListener('pointerdown',event=>{
        if(event.button!==0)return;event.preventDefault();event.stopPropagation();
        const point=svgPoint(event);labelDrag={id:event.pointerId,offsetX:point.x-b.x,offsetY:point.y-b.y};
        group.setPointerCapture(event.pointerId);group.focus({preventScroll:true});$('tooltip').hidden=true;
      });
      group.addEventListener('pointermove',event=>{
        if(labelDrag?.id!==event.pointerId)return;event.preventDefault();event.stopPropagation();
        const point=svgPoint(event);move(point.x-labelDrag.offsetX,point.y-labelDrag.offsetY);
      });
      group.addEventListener('pointerup',event=>{
        if(labelDrag?.id!==event.pointerId)return;event.preventDefault();event.stopPropagation();
        suppressLabelClick=true;labelDrag=null;if(group.hasPointerCapture(event.pointerId))group.releasePointerCapture(event.pointerId);
      });
      group.addEventListener('lostpointercapture',()=>{labelDrag=null;});
      group.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();suppressLabelClick=false;});
      group.addEventListener('keydown',event=>{
        if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
        event.preventDefault();event.stopPropagation();const d=event.shiftKey?12:3;
        move(b.x+(event.key==='ArrowRight'?d:event.key==='ArrowLeft'?-d:0),b.y+(event.key==='ArrowDown'?d:event.key==='ArrowUp'?-d:0));
      });
    }
  }

  function inspect(x,t) {
    selection={x,t};const value=at(x,t),sample=value.sample,s=data.settings;
    const cursor=$('selection');cursor.setAttribute('cx',px(x));cursor.setAttribute('cy',py(t));cursor.setAttribute('visibility','visible');
    $('inspect-empty').hidden=true;$('point-details').hidden=false;$('unpin').hidden=!pinned;
    $('point-temperature').textContent=`${fmt(t,1)} K`;$('point-composition').textContent=`${fmt(x*100,2)} at.% ${symbol(s.components[1])} · ${value.source}`;
    $('gap-banner').hidden=!(value.phases?.length===2&&value.phases[0].phase===value.phases[1].phase);
    const cards=$('phase-cards');cards.replaceChildren();
    for(const p of value.phases||[]) {
      const card=el('article','phase-card'),heading=el('h4','',p.label),swatch=el('span','swatch');swatch.style.background=color(p.phase);heading.prepend(swatch);
      const amount=el('div','amount');amount.append(el('span','','Phase amount (molar)'),el('span','',`${fmt(p.fraction*100,2)}%`));
      const bar=el('div','fraction-bar'),fill=el('span');fill.style.width=`${Math.max(0,Math.min(100,p.fraction*100))}%`;fill.style.background=color(p.phase);bar.append(fill);
      card.append(heading,amount,bar,el('p','composition-line',Object.entries(p.composition).map(([c,f])=>`${symbol(c)} ${fmt(f*100,2)} at.%`).join(' · ')));cards.append(card);
    }
    if(!value.phases?.length)cards.append(el('p','fine','No resolved equilibrium is available here.'));
    const audit=$('point-audit');audit.replaceChildren();
    if(sample) {
      const st=s.temperature_min+(sample.ti+.5)/s.temperature_points*(s.temperature_max-s.temperature_min),sx=(sample.xi+.5)/s.composition_points;
      if(sample.check==='disagreement')audit.append(el('strong','','Independent check: disagreement'));
      audit.append(el('p','fine',`Nearest sample: ${fmt(st,1)} K · ${fmt(sx*100,2)} at.% ${symbol(s.components[1])}. Compared at that sample’s coordinates.`));
      for(const p of sample.phases)audit.append(el('p','fine',`${p.label} · ${fmt(p.fraction*100,2)} mol.% · ${Object.entries(p.composition).map(([c,f])=>`${symbol(c)} ${fmt(f*100,2)} at.%`).join(' / ')}`));
      if(sample.raw_check==='disagreement'||sample.check==='disagreement') {
        audit.append(el('strong','','Boundary prediction at sample:'));
        for(const p of sample.map_phases||[])audit.append(el('p','fine',`${p.label} · ${fmt(p.fraction*100,2)} mol.% · ${Object.entries(p.composition).map(([c,f])=>`${symbol(c)} ${fmt(f*100,2)} at.%`).join(' / ')}`));
      }
    }
    audit.classList.toggle('disagreement',sample?.check==='disagreement');
    return value;
  }
  function locate(event) {const p=$('plot').createSVGPoint();p.x=event.clientX;p.y=event.clientY;const q=p.matrixTransform($('plot').getScreenCTM().inverse()),x=(q.x-plot.left)/plot.width,f=(plot.top+plot.height-q.y)/plot.height;if(x<0||x>1||f<0||f>1)return null;return {x,t:data.settings.temperature_min+f*(data.settings.temperature_max-data.settings.temperature_min)};}
  $('plot').addEventListener('pointermove',event=>{if(!data||!complete||labelDrag||event.target.closest('[data-region-label]'))return;const pos=locate(event);if(!pos){$('tooltip').hidden=true;return;}const value=pinned?at(pos.x,pos.t):inspect(pos.x,pos.t);const tip=$('tooltip');tip.textContent=`${fmt(pos.t)} K · ${fmt(pos.x*100)} at.%\n${key(value.phases)}\n${value.source}`;tip.hidden=false;const rect=$('plot-wrap').getBoundingClientRect();tip.style.left=`${Math.max(0,Math.min(event.clientX-rect.left+12,rect.width-tip.offsetWidth))}px`;tip.style.top=`${Math.max(0,event.clientY-rect.top-tip.offsetHeight-12)}px`;});
  $('plot').addEventListener('pointerleave',()=>$('tooltip').hidden=true);
  $('plot').addEventListener('click',event=>{if(suppressLabelClick){suppressLabelClick=false;return;}if(!data||!complete||labelDrag||event.target.closest('[data-region-label]'))return;const pos=locate(event);if(pos){pinned=true;inspect(pos.x,pos.t);}});
  $('plot').addEventListener('keydown',event=>{if(!data||!complete||event.target.closest('[data-region-label]'))return;const s=data.settings,pos=selection||{x:.5,t:(s.temperature_min+s.temperature_max)/2};if(event.key==='Escape'){pinned=false;$('unpin').hidden=true;return;}if(event.key==='Enter'){event.preventDefault();pinned=!pinned;inspect(pos.x,pos.t);return;}if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const x=Math.min(1,Math.max(0,pos.x+(event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0)/s.composition_points)),t=Math.min(s.temperature_max,Math.max(s.temperature_min,pos.t+(event.key==='ArrowUp'?1:event.key==='ArrowDown'?-1:0)*(s.temperature_max-s.temperature_min)/s.temperature_points));inspect(x,t);});
  $('unpin').addEventListener('click',()=>{pinned=false;$('unpin').hidden=true;});
  $('show-samples').addEventListener('change',()=>{if(data)markers();});
  $('reset-labels').addEventListener('click',()=>{if(!data||!complete)return;labelPositions.clear();$('region-labels').replaceChildren();labels();});
  return {reset() {data=null;complete=false;pinned=false;selection=null;colors.clear();activePhases.clear();colorIndex=0;labelPositions.clear();labelDrag=null;suppressLabelClick=false;$('tooltip').hidden=true;$('legend').replaceChildren();$('diagram-details').hidden=true;}, render(value,finished=true) {
    data=value;complete=finished;pinned=false;selection=null;samples=new Map((data.cells||[]).map(c=>[`${c.xi},${c.ti}`,c]));
    const phases=new Set((data.cells||[]).flatMap(c=>c.phases.map(p=>p.phase)));for(const r of data.boundaries?.ribbons||[])r.ties.forEach(t=>t.phases.forEach(p=>phases.add(p)));for(const b of data.boundaries?.single_phase_bands||[])phases.add(b.phase);
    activePhases=phases; // Keep preview colors stable, but display only current phases.
    for(const p of [...phases].sort())if(!colors.has(p)) {
      const i=p.toUpperCase()==='LIQUID'?0:colorIndex++;
      // Golden-angle hue progression beyond the curated palette.
      const hue=(i*137.508)%360, channel=n=>{
        const k=(n+hue/30)%12,light=.63,a=.31;
        return Math.round(255*(light-a*Math.max(-1,Math.min(k-3,9-k,1)))).toString(16).padStart(2,'0');
      };
      colors.set(p,p.toUpperCase()==='LIQUID'?'#000000':palette[i]||`#${channel(0)}${channel(8)}${channel(4)}`);
    }
    axes();fills();boundaries();markers();if(finished)labels();
    $('empty').hidden=true;$('plot').setAttribute('aria-label',`${data.settings.components.map(symbol).join('-')} equilibrium diagram. Arrow keys inspect; Enter pins; Escape unpins.`);
    $('diagram-details').hidden=false;
    $('legend').replaceChildren();for(const p of [...phases].sort()){const c=color(p);
      const item=el('span','legend-item',p);item.setAttribute('role','listitem');item.style.backgroundColor=c;
      const luminance=rgb(c.slice(1)).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
      item.style.color=luminance>.179?'#000000':'#ffffff';$('legend').append(item);
    }
    const counts=data.validation?.counts||{};
    const entries=[['agreement','Agreement'],['disagreement','Disagreements'],['near_boundary','Near boundary · ignored'],['unverified','Unverified'],['unresolved','Unresolved']];
    $('quality-summary').replaceChildren();
    for(const [type,name]of entries){const count=counts[type]??(data.cells||[]).filter(c=>c.check===type).length;if(!count)continue;
      const stat=el('span',`check-stat check-${type}`);stat.append(el('strong','',count.toLocaleString()),el('span','',count===1&&type==='disagreement'?'Disagreement':name));$('quality-summary').append(stat);}
    $('sample-count').textContent=`${(data.cells||[]).length.toLocaleString()} samples`;
    $('show-samples').disabled=!(data.cells||[]).length;
    $('reset-labels').disabled=!finished;
    $('disagreement-key').hidden=!(data.cells||[]).some(c=>c.check==='disagreement');

    if(finished){$('inspect-empty').hidden=false;$('point-details').hidden=true;}
  }};
}
