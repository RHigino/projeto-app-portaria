'use strict';
// Door maps of the "chaves" module (escaninhos and the two locker rooms), linked to open records.
// Every SVG names its doors armario-001, armario-002…; only one map is in the page at a time.
const ARMARIOS=200;
const MAPS={
  escaninhos:{tab:'Escaninhos',title:'Mapa dos escaninhos',noun:'escaninho',svg:'/escaninhos.svg',width:2464,total:216,field:'escaninho',
    name:{x:104,y:206,max:140},zoom:{start:0.52,minFit:0.38}},
  masculino:{tab:'Armários masculino',title:'Vestiário masculino',noun:'armário',svg:'/vestiario.svg',width:2760,total:ARMARIOS,field:'armario',vestiario:'Masculino',
    name:{x:58,y:158,max:84},zoom:{start:0.52,minFit:0.45},css:'vestiario masculino'},
  feminino:{tab:'Armários feminino',title:'Vestiário feminino',noun:'armário',svg:'/vestiario.svg',width:2760,total:ARMARIOS,field:'armario',vestiario:'Feminino',
    name:{x:58,y:158,max:84},zoom:{start:0.52,minFit:0.45},css:'vestiario feminino'},
};
// Settings keys of the blocked doors, as stored by the server.
const BLOCK_KEYS={escaninhos:'escaninhos_bloqueados',masculino:'armarios_masculino_bloqueados',feminino:'armarios_feminino_bloqueados'};
const ZOOM_LEVELS=[0.35,0.52,0.75,1,1.5,2];
const SVG_NS='http://www.w3.org/2000/svg';
const mapView={current:'escaninhos',shown:false,markup:{},place:{}};  // markup per SVG file; place: zoom and scroll per map

const doorId=n=>'armario-'+String(n).padStart(3,'0');
const capital=text=>text[0].toUpperCase()+text.slice(1);
const isActiveLink=r=>r.module==='chaves'&&r.status==='Em aberto'&&!r.payload.devolucao;
const onMap=(r,m)=>Boolean(r.payload[m.field])&&(!m.vestiario||r.payload.vestiario===m.vestiario);

function holders(key){const m=MAPS[key];return new Map(state.records.filter(r=>isActiveLink(r)&&onMap(r,m)).map(r=>[Number(r.payload[m.field]),r]))}
function blockedDoors(key){try{return new Set(JSON.parse(state.settings[BLOCK_KEYS[key]]||'[]'))}catch{return new Set()}}
function doorStatus(n,held,blocked){return held.has(n)?'ocupado':blocked.has(n)?'bloqueado':'livre'}
function freeDoors(key){const held=holders(key),blocked=blockedDoors(key);return Array.from({length:MAPS[key].total},(_,i)=>i+1).filter(n=>doorStatus(n,held,blocked)==='livre')}
function doorCounts(key){
  const held=holders(key),blocked=blockedDoors(key),counts={livre:0,ocupado:0,bloqueado:0};
  for(let n=1;n<=MAPS[key].total;n++)counts[doorStatus(n,held,blocked)]++;
  return counts;
}
const plural=(n,one,many)=>`${n} ${n===1?one:many}`;
const countsText=c=>`${plural(c.livre,'livre','livres')} · ${plural(c.ocupado,'ocupado','ocupados')} · ${plural(c.bloqueado,'bloqueado','bloqueados')}`;
const occupancy=key=>doorCounts(key).ocupado/MAPS[key].total*100;
const percent=value=>value.toLocaleString('pt-BR',{maximumFractionDigits:1})+'%';

// Number input of the record form; the free doors are offered as suggestions.
function doorInput(key,attrs,value){
  const total=key==='escaninho'?MAPS.escaninhos.total:ARMARIOS;
  return `<input ${attrs} type="number" min="1" max="${total}" step="1" inputmode="numeric" list="livres-${key}" value="${esc(value)}"><datalist id="livres-${key}">${key==='escaninho'?freeDoors('escaninhos').map(n=>`<option value="${n}">`).join(''):''}</datalist>`;
}
function bindDoorForm(){
  const room=$('#f-vestiario'),list=$('#livres-armario');if(!room||!list)return;
  const fill=()=>{list.innerHTML=room.value?freeDoors(room.value.toLowerCase()).map(n=>`<option value="${n}">`).join(''):''};
  room.addEventListener('change',fill);fill();
}

function mapPanel(){
  const m=MAPS[mapView.current];
  const tabs=Object.entries(MAPS).map(([key,t])=>`<button class="maptab ${key===mapView.current?'active':''}" role="tab" aria-selected="${key===mapView.current}" data-action="esc-tab" data-map="${key}">${esc(t.tab)}<small>${percent(occupancy(key))}</small></button>`).join('');
  return `<section class="panel escpanel"><div class="maptabs" role="tablist" aria-label="Escolha o mapa">${tabs}</div><div class="paneltitle"><div><h2>${esc(m.title)}</h2><p>Clique em uma porta para ver o cadastro, vincular um colaborador ou liberar o ${m.noun}.</p></div><div class="escstats"><div class="escocup" title="Portas ocupadas em relação ao total de ${m.total}"><span>Ocupação</span><strong id="esc-pct"></strong><div class="escbarra" aria-hidden="true"><i id="esc-bar"></i></div></div><span class="pill" id="esc-count"></span></div></div>
  <div class="escbar"><div class="esclegend"><span><i class="livre"></i>Livre</span><span><i class="ocupado"></i>Ocupado</span><span><i class="bloqueado"></i>Bloqueado</span></div>
  <div class="esctools"><input id="esc-go" type="number" min="1" max="${m.total}" step="1" inputmode="numeric" placeholder="Nº" aria-label="Número da porta para localizar"><button class="btn" data-action="esc-go">${icon('search')} Localizar</button>
  <button class="iconbtn" data-action="esc-zoomout" title="Diminuir zoom" aria-label="Diminuir zoom">${icon('minus')}</button><span class="pill" id="esc-zoom" aria-live="polite"></span><button class="iconbtn" data-action="esc-zoomin" title="Aumentar zoom" aria-label="Aumentar zoom">${icon('plus')}</button><button class="iconbtn" data-action="esc-fit" title="Ver o mapa inteiro" aria-label="Ver o mapa inteiro">${icon('fit')}</button></div></div>
  <div class="escmap ${m.css||''}" id="escmap"><p class="escloading">Carregando mapa…</p></div></section>`;
}

function shortName(name){const parts=String(name||'').trim().split(/\s+/);const text=parts.length>1?`${parts[0]} ${parts[parts.length-1][0]}.`:parts[0];return text.length>10?text.slice(0,9)+'…':text}

function nameLabel(door,m,name){
  const t=document.createElementNS(SVG_NS,'text');
  t.setAttribute('class','escnome');t.setAttribute('x',m.name.x);t.setAttribute('y',m.name.y);t.setAttribute('text-anchor','middle');
  t.textContent=shortName(name);door.appendChild(t);
  // Long names are squeezed so they never reach the lock, pin or hinges drawn on the door.
  if(t.getComputedTextLength()>m.name.max){t.setAttribute('textLength',m.name.max);t.setAttribute('lengthAdjust','spacingAndGlyphs')}
}

function paintMap(){
  if(!$('#escmap svg'))return;
  const key=mapView.current,m=MAPS[key],held=holders(key),blocked=blockedDoors(key),Noun=capital(m.noun);
  for(let n=1;n<=m.total;n++){
    const door=document.getElementById(doorId(n));if(!door)continue;
    const status=doorStatus(n,held,blocked),r=held.get(n);
    door.dataset.status=status;
    door.querySelector('.escnome')?.remove();
    const label=r?`${Noun} ${n}, ocupado por ${r.payload.nome}`:`${Noun} ${n}, ${status}`;
    door.setAttribute('aria-label',label);
    const title=door.querySelector('title');if(title)title.textContent=r?`${Noun} ${n} — ${r.payload.nome}${r.payload.setor?' ('+r.payload.setor+')':''}`:label;
    if(r)nameLabel(door,m,r.payload.nome);
  }
  const counts=doorCounts(key),rate=counts.ocupado/m.total*100;
  $('#esc-count').textContent=countsText(counts);
  $('#esc-pct').textContent=percent(rate);
  $('#esc-bar').style.width=rate+'%';
  for(const tab of document.querySelectorAll('.maptab'))tab.querySelector('small').textContent=percent(occupancy(tab.dataset.map));
}

// Both locker rooms share vestiario.svg: name the room shown in its heading and label.
function titleRoom(box,room){
  const heading=[...box.querySelectorAll('svg text')].find(t=>t.textContent.startsWith('VESTIÁRIO'));
  if(heading)heading.textContent='VESTIÁRIO '+room.toUpperCase();
  box.querySelector('svg').setAttribute('aria-label',`Vestiário ${room.toLowerCase()}, armários 1 a ${ARMARIOS}`);
}

const place=()=>mapView.place[mapView.current]??={zoom:null,left:0,top:0};
// offsetWidth minus the 2px border: the width once the fitted map no longer needs a scrollbar.
const fitZoom=()=>Math.max(0.1,($('#escmap').offsetWidth-2)/MAPS[mapView.current].width);
function applyZoom(zoom,keepCenter=true){
  const box=$('#escmap'),svg=$('#escmap svg');if(!box||!svg)return;
  const cx=(box.scrollLeft+box.clientWidth/2)/svg.clientWidth,cy=(box.scrollTop+box.clientHeight/2)/svg.clientHeight;
  place().zoom=zoom;svg.style.width=Math.round(MAPS[mapView.current].width*zoom)+'px';
  box.classList.toggle('zoomed',zoom>fitZoom()+0.005);  // scrollbars only once the map is wider than the screen
  if(keepCenter){box.scrollLeft=cx*svg.clientWidth-box.clientWidth/2;box.scrollTop=cy*svg.clientHeight-box.clientHeight/2}
  $('#esc-zoom').textContent=Math.round(zoom*100)+'%';
}
function stepZoom(direction){const z=place().zoom,next=direction>0?ZOOM_LEVELS.find(v=>v>z+0.001):[...ZOOM_LEVELS].reverse().find(v=>v<z-0.001);applyZoom(next??z)}

async function mountMap(){
  const box=$('#escmap');if(!box){mapView.shown=false;return}
  // Entering the tab: other computers may have changed the map since the last load.
  const entering=!mapView.shown;mapView.shown=true;
  const key=mapView.current,m=MAPS[key];
  try{
    if(!mapView.markup[m.svg]){const res=await fetch(m.svg);if(!res.ok)throw new Error();mapView.markup[m.svg]=await res.text()}
  }catch{box.innerHTML='<p class="escloading">Não foi possível carregar o mapa. Atualize a página.</p>';return}
  if(!document.body.contains(box)||key!==mapView.current)return;  // page or map changed while loading
  box.innerHTML=mapView.markup[m.svg];
  if(m.vestiario)titleRoom(box,m.vestiario);
  const spot=place();
  if(spot.zoom===null){const fit=fitZoom();spot.zoom=fit>=m.zoom.minFit?Math.min(m.zoom.start,fit):m.zoom.start}
  paintMap();applyZoom(spot.zoom,false);box.scrollLeft=spot.left;box.scrollTop=spot.top;
  box.onscroll=()=>{spot.left=box.scrollLeft;spot.top=box.scrollTop};
  const open=e=>{const door=e.target.closest('.armario');if(door)doorModal(Number(door.dataset.numero))};
  box.onclick=open;
  box.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(e)}};
  $('#esc-go').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();goToDoor()}};
  if(entering)refreshMap().catch(err=>toast(err.message,true));
}

function goToDoor(){
  const n=Number($('#esc-go').value),total=MAPS[mapView.current].total;
  if(!Number.isInteger(n)||n<1||n>total){toast(`Informe um número de 1 a ${total}.`,true);return}
  const box=$('#escmap'),door=box.querySelector('#'+doorId(n));if(!door)return;
  const b=box.getBoundingClientRect(),d=door.getBoundingClientRect();
  box.scrollTo({left:box.scrollLeft+d.left-b.left-(b.width-d.width)/2,top:box.scrollTop+d.top-b.top-(b.height-d.height)/2,behavior:'smooth'});
  if(!box.classList.contains('zoomed'))door.scrollIntoView({block:'center',behavior:'smooth'});  // tall maps scroll the page instead
  door.focus({preventScroll:true});door.classList.add('escflash');setTimeout(()=>door.classList.remove('escflash'),1800);
}

// Other doors held by the same record, released together with it.
function otherLinks(r,key){
  const links=[];
  if(key!=='escaninhos'&&r.payload.escaninho)links.push(`escaninho ${r.payload.escaninho}`);
  if(r.payload.armario&&r.payload.vestiario&&MAPS[key].vestiario!==r.payload.vestiario)links.push(`armário ${r.payload.vestiario.toLowerCase()} ${r.payload.armario}`);
  return links;
}

function doorModal(n){
  const key=mapView.current,m=MAPS[key],r=holders(key).get(n),Noun=capital(m.noun);
  const status=doorStatus(n,holders(key),blockedDoors(key)),where=m.vestiario?` · vestiário ${m.vestiario.toLowerCase()}`:'';
  const close='<button class="btn" data-action="close">Fechar</button>';
  if(r){
    const fields=moduleBy('chaves').fields,rows=fields.filter(f=>r.payload[f[0]]).map(f=>`<div><small>${esc(f[1])}</small><p>${esc(f[2]==='datetime-local'?fmt(r.payload[f[0]]):r.payload[f[0]])}</p></div>`).join('');
    const others=otherLinks(r,key),note=others.length?`<div class="notice">Este cadastro também ocupa ${esc(others.join(' e '))}. Liberar encerra o cadastro inteiro e libera tudo.</div>`:'';
    openModal(`${Noun} ${n} · ocupado`,'Cadastro vinculado a esta porta'+where+'.',`<div class="modalbody">${note}<div class="detailgrid">${rows}<div><small>Cadastrado por</small><p>${esc(r.creator)} · ${fmt(r.created_at)}</p></div></div></div>`,
      `<div class="modalfoot">${close}<button class="btn" data-action="view" data-id="${r.id}">${icon('eye')} Registro completo</button>${canReturn(r)?`<button class="btn primary" data-action="return" data-id="${r.id}">${icon('return')} Liberar ${m.noun}</button>`:''}</div>`);
    return;
  }
  const blocked=status==='bloqueado';
  const text=blocked?`Este ${m.noun} está bloqueado pelo administrador e não aceita novos vínculos até ser desbloqueado.`:`Este ${m.noun} está livre e pode ser vinculado a um colaborador.`;
  const adminButton=isAdmin()?`<button class="btn" data-action="${blocked?'esc-unblock':'esc-block'}" data-n="${n}">${icon('lock')} ${blocked?'Desbloquear':'Bloquear'}</button>`:'';
  openModal(`${Noun} ${n} · ${status}`,'Situação atual da porta'+where+'.',`<div class="modalbody"><div class="notice">${text}</div></div>`,
    `<div class="modalfoot">${close}${adminButton}${blocked?'':`<button class="btn primary" data-action="esc-link" data-n="${n}">${icon('plus')} Vincular colaborador</button>`}</div>`);
}

async function refreshMap(){await loadData();paintMap();const table=$('#record-table');if(table)table.innerHTML=recordTable()}

document.addEventListener('click',async e=>{
  const button=e.target.closest('[data-action^="esc-"]');if(!button)return;
  const action=button.dataset.action,n=Number(button.dataset.n),key=mapView.current,m=MAPS[key];
  try{
    switch(action){
      case 'esc-tab':if(button.dataset.map!==key){mapView.current=button.dataset.map;render()}break;
      case 'esc-link':$('#modal').close();recordForm(null,'chaves',m.vestiario?{vestiario:m.vestiario,armario:String(n)}:{escaninho:String(n)});break;
      case 'esc-block':case 'esc-unblock':
        button.disabled=true;
        await api('mapas/bloqueio',{method:'POST',body:JSON.stringify({mapa:key,numero:n,bloqueado:action==='esc-block'})});
        $('#modal').close();await refreshMap();toast(`${capital(m.noun)} ${n} ${action==='esc-block'?'bloqueado':'desbloqueado'}.`);break;
      case 'esc-go':goToDoor();break;
      case 'esc-zoomin':stepZoom(1);break;
      case 'esc-zoomout':stepZoom(-1);break;
      case 'esc-fit':applyZoom(fitZoom(),false);break;
    }
  }catch(err){toast(err.message,true);button.disabled=false}
});
