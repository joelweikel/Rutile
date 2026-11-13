// Vector boundaries over a display raster. Pixel count never changes solver resolution.
const NS = 'http://www.w3.org/2000/svg';
const $ = id => document.getElementById(id);
const palette = ['#29d9ed', '#ff6f59', '#b790ff', '#ffd24c', '#42e69b', '#ff70be', '#538fff', '#b8e54b', '#ff9e42', '#48ded0', '#df85fa', '#f3df93', '#d8edff'];
const plot = {left:76, top:25, width:670, height:465};
const labelFontSize = 11;
const labelLineHeight = 14;
const fmt = (v,d=1) => Number.isFinite(v) ? v.toLocaleString(undefined,{maximumFractionDigits:d}) : 'Unavailable';
const symbol = value => value[0]+value.slice(1).toLowerCase();
const key = phases => phases?.map(p=>p.label).sort().join(' + ') || 'Unresolved';
const structureNames = new Map([['FCC_A1','FCC'], ['BCC_A2','BCC'], ['HCP_A3','HCP'], ['LIQUID','Liquid']]);
// These additional prototypes are documented in the bundled assessments.
const assessmentStructures = new Map([
  ['bd06016e51db2bef626a65b9f3a00b660e9b1c8a7c8c10e4d0ad8867809c62e4', new Map([
    ['AL2CU_C16','C16'], ['ALCU_ETA_LT','mC20'], ['ALCU_ETA_HT','oC32'], ['AL3CU4_LT','oI24'],
    ['AL3CU4_HT','oF88'], ['ALCU_B82','B8₂'], ['AL5CU8','hR52'], ['GAMMA_D83','D8₃'],
    ['GAMMA_D82','D8₂'], ['ALCU3_D022','D0₂₂']
  ])],
  ['d374ef87267bcebeb4c0bc9329c20dea5b669ed49fa13d9894c0ce8af135c4b0', new Map([
    ['CHI_A12','A12'], ['SIGMA_D8B','D8ᵦ'], ['SIGMA_OLD','tP30']
  ])]
]);
const phaseComposition = phase => Object.entries(phase.composition).map(([c,f])=>`${symbol(c)} ${fmt(f*100,2)}`).join(' · ')+' at%';
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
  function endLabelDrag() {
    labelDrag=null;
    $('workspace').removeAttribute('data-label-dragging');
    $('unpin').inert=false;
  }
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
    root.append(defs);
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
    const measure=document.createElement('canvas').getContext('2d');
    measure.font=`600 ${labelFontSize}px Estedad, sans-serif`;
    function box(name,x,y) {
      const lines=name.split(' + ');
      const width=Math.ceil(Math.max(...lines.map(line=>measure.measureText(line).width)))+10;
      return {name,x,y,width,height:lines.length*labelLineHeight+4,lines};
    }
    const overlaps=b=>placed.some(p=>Math.abs(p.x-b.x)<(p.width+b.width)/2+4&&Math.abs(p.y-b.y)<(p.height+b.height)/2+4);
    const insideBox=(point,b,gap=0)=>Math.abs(point.x-b.x)<b.width/2+gap&&Math.abs(point.y-b.y)<b.height/2+gap;
    const gridBox=(b,padding=0)=>({
      left:Math.floor((b.x-b.width/2-padding-plot.left)/plot.width*nx),
      right:Math.floor((b.x+b.width/2+padding-plot.left)/plot.width*nx),
      bottom:Math.floor((plot.top+plot.height-b.y-b.height/2-padding)/plot.height*nt),
      top:Math.floor((plot.top+plot.height-b.y+b.height/2+padding)/plot.height*nt)
    });
    const insidePlot=({left,right,bottom,top})=>left>=0&&right<nx&&bottom>=0&&top<nt;
    function fitsField(b,name) {
      const bounds=gridBox(b,2);
      if(!insidePlot(bounds))return false;
      for(let y=bounds.bottom;y<=bounds.top;y++)for(let x=bounds.left;x<=bounds.right;x++)if(lattice[y*nx+x]!==name)return false;
      return true;
    }
    for(const region of [...regions.values()].sort((a,b)=>b.indices.length-a.indices.length)) {
      // Prefer a point with room on each side, rather than the centroid of a crescent.
      const candidates=region.indices.map(i=>{const xi=i%nx,ti=Math.floor(i/nx);let distance=0;while(distance<20&&xi-distance>=0&&xi+distance<nx&&ti-distance>=0&&ti+distance<nt&&[i-distance,i+distance,i-distance*nx,i+distance*nx].every(j=>lattice[j]===region.name))distance++;return {i,distance};}).sort((a,b)=>b.distance-a.distance);
      const shape=box(region.name,0,0);
      let anchor=candidates[0],chosen;
      for(const c of candidates) {
        const b={...shape,x:px((c.i%nx+.5)/nx),y:plot.top+plot.height-(Math.floor(c.i/nx)+.5)/nt*plot.height};
        if(!overlaps(b)&&fitsField(b,region.name)){chosen=b;anchor=c;break;}
      }
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
    function leaderStart(b) {
      const dx=b.anchor.x-b.x,dy=b.anchor.y-b.y;
      const edge=Math.min(1,(b.width/2+2)/(Math.abs(dx)||1e-9),(b.height/2+2)/(Math.abs(dy)||1e-9));
      return {x:b.x+dx*edge,y:b.y+dy*edge};
    }
    function crosses(a,b,c,d) {
      const side=(p,q,r)=>(q.x-p.x)*(r.y-p.y)-(q.y-p.y)*(r.x-p.x);
      return side(a,b,c)*side(a,b,d)<0&&side(c,d,a)*side(c,d,b)<0;
    }
    function lineHitsBox(start,end,b) {
      const a={x:b.x-b.width/2,y:b.y-b.height/2},c={x:b.x+b.width/2,y:b.y+b.height/2};
      const corners=[a,{x:c.x,y:a.y},c,{x:a.x,y:c.y}];
      return insideBox(start,b)||insideBox(end,b)||corners.some((p,i)=>crosses(start,end,p,corners[(i+1)%4]));
    }
    const external=[];
    const localLeaders=[];
    for(const anchor of callouts) {
      const shape=box(anchor.name,anchor.x,anchor.y);
      // Search around the field and prefer short leaders in open space.
      let chosen, best=Infinity;
      for(let dy=-90;dy<=90;dy+=10)for(let dx=-110;dx<=110;dx+=10) {
        const b={...shape,x:anchor.x+dx,y:anchor.y+dy,anchor,placement:'nearby'};
        if(!insidePlot(gridBox(b,3))||overlaps(b)||callouts.some(point=>insideBox(point,b,8)))continue;
        const start=leaderStart(b);
        const length=Math.hypot(start.x-anchor.x,start.y-anchor.y);
        if(length<8||length>85||length>=best)continue;
        if(placed.some(p=>lineHitsBox(start,anchor,p)))continue;
        if(localLeaders.some(line=>crosses(start,anchor,line.start,line.end)||lineHitsBox(line.start,line.end,b)))continue;
        chosen=b;best=length;
      }
      if(chosen) {
        placed.push(chosen);
        localLeaders.push({start:leaderStart(chosen),end:anchor});
      } else external.push({...shape,anchor,placement:'margin'});
    }
    external.sort((a,b)=>a.y-b.y);
    let edge=plot.top-8;
    for(const b of external) {
      b.x=plot.left+plot.width+18+b.width/2;
      b.y=Math.max(b.y,edge+8+b.height/2);
      edge=b.y+b.height/2;
    }
    placed.push(...external);
    $('plot').setAttribute('viewBox',`0 0 ${Math.max(780,...external.map(b=>b.x+b.width/2+12))} ${Math.max(580,...external.map(b=>b.y+b.height/2+12))}`);
    const leaders=svg('g',{'pointer-events':'none'});
    $('region-labels').append(leaders);
    const svgPoint=event=>{const p=$('plot').createSVGPoint();p.x=event.clientX;p.y=event.clientY;return p.matrixTransform($('plot').getScreenCTM().inverse());};
    for(const b of placed) {
      b.anchor??={x:b.x,y:b.y};b.placement??='field';
      const saved=labelPositions.get(b.name);if(saved){b.x=saved.x;b.y=saved.y;b.placement='manual';}
      const group=svg('g',{'data-region-label':b.name,'data-label-placement':b.placement,tabindex:0,role:'button','aria-label':`Move ${b.name} label. Drag or use arrow keys; Shift moves farther.`,class:'phase-region-label'});
      const leader=svg('g');
      const shadow=svg('line',{stroke:'#101622','stroke-width':2.6});
      const line=svg('line',{stroke:'#eff5ff','stroke-width':1});
      const dot=svg('circle',{cx:b.anchor.x,cy:b.anchor.y,r:2.4,fill:'#eff5ff',stroke:'#101622','stroke-width':1});
      leader.append(shadow,line,dot);leaders.append(leader);
      const rect=svg('rect',{width:b.width,height:b.height,rx:4,fill:'transparent'});
      const text=b.lines.map(line=>svg('text',{'text-anchor':'middle','font-size':labelFontSize},line));
      function position() {
        group.dataset.labelX=b.x;group.dataset.labelY=b.y;
        rect.setAttribute('x',b.x-b.width/2);rect.setAttribute('y',b.y-b.height/2);
        text.forEach((node,i)=>{node.setAttribute('x',b.x);node.setAttribute('y',b.y+(i-(b.lines.length-1)/2)*labelLineHeight+labelFontSize/3);});
        const start=leaderStart(b);
        for(const segment of [shadow,line]) {
          segment.setAttribute('x1',start.x);segment.setAttribute('y1',start.y);
          segment.setAttribute('x2',b.anchor.x);segment.setAttribute('y2',b.anchor.y);
        }
        leader.style.display=insideBox(b.anchor,b,2)?'none':'';
      }
      function move(x,y) {
        const height=$('plot').viewBox.baseVal.height;
        b.x=Math.max(b.width/2+3,Math.min($('plot').viewBox.baseVal.width-3-b.width/2,x));b.y=Math.max(b.height/2+3,Math.min(height-b.height/2-3,y));
        labelPositions.set(b.name,{x:b.x,y:b.y});group.dataset.labelPlacement='manual';position();
      }
      group.append(rect,...text);position();$('region-labels').append(group);
      group.addEventListener('pointerdown',event=>{
        if(event.button!==0||labelDrag)return;event.preventDefault();event.stopPropagation();
        const point=svgPoint(event);labelDrag={id:event.pointerId,offsetX:point.x-b.x,offsetY:point.y-b.y};
        group.setPointerCapture(event.pointerId);group.focus({preventScroll:true});$('tooltip').hidden=true;
        if(!pinned)$('selection').setAttribute('data-obscured','');
        $('workspace').setAttribute('data-label-dragging','');
        $('unpin').inert=true;
      });
      group.addEventListener('pointermove',event=>{
        if(labelDrag?.id!==event.pointerId)return;event.preventDefault();event.stopPropagation();
        const point=svgPoint(event);move(point.x-labelDrag.offsetX,point.y-labelDrag.offsetY);
      });
      group.addEventListener('pointerup',event=>{
        if(labelDrag?.id!==event.pointerId)return;event.preventDefault();event.stopPropagation();
        suppressLabelClick=true;
        endLabelDrag();
        if(group.hasPointerCapture(event.pointerId))group.releasePointerCapture(event.pointerId);
        // A captured pointer can release outside the label without a click.
        setTimeout(()=>{suppressLabelClick=false;},0);
      });
      group.addEventListener('lostpointercapture',event=>{if(labelDrag?.id===event.pointerId)endLabelDrag();});
      group.addEventListener('pointercancel',event=>{if(labelDrag?.id===event.pointerId)endLabelDrag();});
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
    cursor.removeAttribute('data-obscured');
    $('inspect-empty').hidden=true;$('point-details').hidden=false;$('unpin').hidden=!pinned;
    const documented=assessmentStructures.get(data.provenance?.sha256);
    $('point-structure').textContent=value.phases?.map(p=>{
      const name=documented?.get(p.phase)||structureNames.get(p.phase)||p.phase;
      return name+p.label.slice(p.phase.length);
    }).join(' + ')||'Unresolved';
    $('point-temperature').textContent=`${fmt(t,1)} K`;
    $('point-composition').textContent=`${fmt(x*100,2)} at% ${symbol(s.components[1])}`;
    $('gap-banner').hidden=!(value.phases?.length===2&&value.phases[0].phase===value.phases[1].phase);
    const cards=$('phase-cards');cards.replaceChildren();
    for(const p of value.phases||[]) {
      const card=el('article','phase-card'),heading=el('h4','',p.label),swatch=el('span','swatch');swatch.style.background=color(p.phase);heading.prepend(swatch);
      const amount=el('strong','amount',`${fmt(p.fraction*100,2)} mol%`);
      const bar=el('div','fraction-bar'),fill=el('span');fill.style.width=`${Math.max(0,Math.min(100,p.fraction*100))}%`;fill.style.background=color(p.phase);bar.append(fill);
      const header=el('div','phase-card-heading');header.append(heading,amount);
      card.append(header,bar,el('p','composition-line',phaseComposition(p)));cards.append(card);
    }
    const audit=$('point-audit'), content=$('point-audit-content');
    content.replaceChildren(el('p','',value.source));
    const check=sample?.check;
    const differs=sample?.raw_check==='disagreement'||check==='disagreement';
    const state={disagreement:'Sample disagreement',near_boundary:'Near-boundary difference (ignored)',unverified:'Unverified sample',unresolved:'Unresolved sample'}[check];
    $('point-audit-title').textContent=state||'Point details';
    audit.classList.toggle('disagreement',check==='disagreement');
    if(sample) {
      const st=s.temperature_min+(sample.ti+.5)/s.temperature_points*(s.temperature_max-s.temperature_min),sx=(sample.xi+.5)/s.composition_points;
      content.append(el('p','',`Nearest sample · ${fmt(st,1)} K · ${fmt(sx*100,2)} at% ${symbol(s.components[1])}`));
      if(value.prediction||differs)for(const p of sample.phases) {
        content.append(el('p','',`${p.label} · ${fmt(p.fraction*100,2)} mol% · ${phaseComposition(p)}`));
      }
      if(differs) {
        content.append(el('strong','','Boundary prediction at sample'));
        for(const p of sample.map_phases||[])content.append(el('p','',`${p.label} · ${fmt(p.fraction*100,2)} mol% · ${phaseComposition(p)}`));
      }
    }
  }
  function locate(event) {const p=$('plot').createSVGPoint();p.x=event.clientX;p.y=event.clientY;const q=p.matrixTransform($('plot').getScreenCTM().inverse()),x=(q.x-plot.left)/plot.width,f=(plot.top+plot.height-q.y)/plot.height;if(x<0||x>1||f<0||f>1)return null;return {x,t:data.settings.temperature_min+f*(data.settings.temperature_max-data.settings.temperature_min)};}
  $('plot').addEventListener('pointermove',event=>{
    if(!data||!complete||labelDrag)return;
    const tip=$('tooltip'), pos=locate(event);
    if(event.target.closest('[data-region-label]')){
      tip.hidden=true;
      if(!pinned)$('selection').setAttribute('data-obscured','');
      return;
    }
    if(!pos){tip.hidden=true;return;}
    if(!pinned){tip.hidden=true;inspect(pos.x,pos.t);return;}
    tip.textContent=`${fmt(pos.t)} K · ${fmt(pos.x*100)} at% ${symbol(data.settings.components[1])}\n${key(at(pos.x,pos.t).phases)}`;
    tip.hidden=false;
    const rect=$('plot-wrap').getBoundingClientRect();
    tip.style.left=`${Math.max(0,Math.min(event.clientX-rect.left+12,rect.width-tip.offsetWidth))}px`;
    tip.style.top=`${Math.max(0,event.clientY-rect.top-tip.offsetHeight-12)}px`;
  });
  $('plot').addEventListener('pointerleave',()=>$('tooltip').hidden=true);
  $('plot').addEventListener('click',event=>{if(suppressLabelClick){suppressLabelClick=false;return;}if(!data||!complete||labelDrag||event.target.closest('[data-region-label]'))return;const pos=locate(event);if(pos){pinned=true;$('tooltip').hidden=true;inspect(pos.x,pos.t);}});
  $('plot').addEventListener('keydown',event=>{if(!data||!complete||event.target.closest('[data-region-label]'))return;const s=data.settings,pos=selection||{x:.5,t:(s.temperature_min+s.temperature_max)/2};if(event.key==='Escape'){pinned=false;$('unpin').hidden=true;return;}if(event.key==='Enter'){event.preventDefault();pinned=!pinned;inspect(pos.x,pos.t);return;}if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const x=Math.min(1,Math.max(0,pos.x+(event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0)/s.composition_points)),t=Math.min(s.temperature_max,Math.max(s.temperature_min,pos.t+(event.key==='ArrowUp'?1:event.key==='ArrowDown'?-1:0)*(s.temperature_max-s.temperature_min)/s.temperature_points));inspect(x,t);});
  $('unpin').addEventListener('click',()=>{pinned=false;$('unpin').hidden=true;$('tooltip').hidden=true;$('plot').focus({preventScroll:true});});
  $('show-samples').addEventListener('change',()=>{if(data)markers();});
  $('reset-labels').addEventListener('click',()=>{if(!data||!complete)return;labelPositions.clear();$('region-labels').replaceChildren();labels();});
  return {reset() {
    data=null;complete=false;pinned=false;selection=null;colors.clear();activePhases.clear();colorIndex=0;
    labelPositions.clear();endLabelDrag();suppressLabelClick=false;$('tooltip').hidden=true;$('legend').replaceChildren();
    $('diagram-details').hidden=true;$('phase-key').hidden=true;$('phase-key').open=false;
    $('sample-summary').open=false;$('point-audit').open=false;
  }, render(value,finished=true) {
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
    const phaseKey=$('phase-key');
    const legendParent=finished?$('inspector'):$('preview-legend');
    if(phaseKey.parentElement!==legendParent)legendParent.append(phaseKey);
    phaseKey.classList.toggle('panel',finished);
    phaseKey.hidden=!phases.size;
    if(finished)phaseKey.open=false;
    $('legend').replaceChildren();for(const p of [...phases].sort()){const c=color(p);
      const item=el('span','legend-item',p);item.setAttribute('role','listitem');item.style.backgroundColor=c;
      const luminance=rgb(c.slice(1)).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
      item.style.color=luminance>.179?'#000000':'#ffffff';$('legend').append(item);
    }
    const counts=data.validation?.counts||{};
    const entries=[['agreement','Agreement'],['disagreement','Disagreements'],['near_boundary','Near boundary · ignored'],['unverified','Unverified'],['unresolved','Unresolved']];
    $('quality-summary').replaceChildren();
    const alerts=[];
    for(const [type,name]of entries){const count=counts[type]??(data.cells||[]).filter(c=>c.check===type).length;if(!count)continue;
      const label=count===1&&type==='disagreement'?'Disagreement':name;
      const stat=el('span',`check-stat check-${type}`);stat.append(el('strong','',count.toLocaleString()),el('span','',label));$('quality-summary').append(stat);
      if(type==='disagreement'||type==='unverified'||type==='unresolved')alerts.push(`${count.toLocaleString()} ${label.toLowerCase()}`);
    }
    $('sample-count').textContent=`${(data.cells||[]).length.toLocaleString()} samples`;
    $('check-alert').textContent=alerts.join(' · ');
    $('check-alert').hidden=!alerts.length;
    $('show-samples').disabled=!(data.cells||[]).length;
    $('reset-labels').hidden=!finished;
    $('disagreement-key').hidden=!(data.cells||[]).some(c=>c.check==='disagreement');

    if(finished){$('inspect-empty').hidden=false;$('point-details').hidden=true;$('unpin').hidden=true;$('point-structure').textContent='Phase inspector';}
  }};
}
