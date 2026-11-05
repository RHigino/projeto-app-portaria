'use strict';
// Door maps of the "chaves" module (escaninhos and the two locker rooms), linked to open records.
// Every SVG names its doors armario-001, armario-002…; only one map is in the page at a time.
const ARMARIOS=300;
const FIRST_FEMALE_LOCKER=157;
const MAPS={
  escaninhos:{tab:'Escaninhos',title:'Mapa dos escaninhos',noun:'escaninho',svg:'/escaninhos.svg',width:2464,first:1,last:216,field:'escaninho',
    name:{x:104,y:206,max:140},badge:{x:28,y:98,w:88,h:36,font:26},zoom:{start:0.52,minFit:0.38}},
  masculino:{tab:'Armários masculino',title:'Vestiário masculino',noun:'armário',svg:'/vestiario.svg',width:2760,first:1,last:ARMARIOS,field:'armario',vestiario:'Masculino',
    name:{x:58,y:158,max:84},badge:{x:10,y:53,w:58,h:22,font:15},zoom:{start:0.52,minFit:0.45},css:'vestiario masculino'},
  feminino:{tab:'Armários feminino',title:'Vestiário feminino',noun:'armário',svg:'/vestiario.svg',width:2760,first:FIRST_FEMALE_LOCKER,last:ARMARIOS,field:'armario',vestiario:'Feminino',
    name:{x:58,y:158,max:84},badge:{x:10,y:53,w:58,h:22,font:15},zoom:{start:0.52,minFit:0.45},css:'vestiario feminino'},
};
// Settings keys of the blocked doors, as stored by the server.
const BLOCK_KEYS={escaninhos:'escaninhos_bloqueados',masculino:'armarios_masculino_bloqueados',feminino:'armarios_feminino_bloqueados'};
const THIRD_PARTY_KEYS={escaninhos:'terceirizados_escaninhos',masculino:'terceirizados_masculino',feminino:'terceirizados_feminino'};
const ROOM_NOTE_HEIGHT=300,ROOM_FOOT_MARGIN=50;  // space of the note below a cropped room, and of its last line
const ZOOM_LEVELS=[0.35,0.52,0.75,1,1.5,2];
const SVG_NS='http://www.w3.org/2000/svg';
const mapView={current:'escaninhos',shown:false,markup:{},place:{}};  // markup per SVG file; place: zoom and scroll per map

const doorCount=m=>m.last-m.first+1;
const doorNumbers=m=>Array.from({length:doorCount(m)},(_,i)=>m.first+i);
const doorId=n=>'armario-'+String(n).padStart(3,'0');
const capital=text=>text[0].toUpperCase()+text.slice(1);
const isActiveLink=r=>r.module==='chaves'&&r.status==='Em aberto'&&!r.payload.devolucao;
const onMap=(r,m)=>Boolean(r.payload[m.field])&&(!m.vestiario||r.payload.vestiario===m.vestiario);

function holders(key){const m=MAPS[key];return new Map(state.records.filter(r=>isActiveLink(r)&&onMap(r,m)).map(r=>[Number(r.payload[m.field]),r]))}
function blockedDoors(key){try{return new Set(JSON.parse(state.settings[BLOCK_KEYS[key]]||'[]'))}catch{return new Set()}}
// {door number: {motivo, por, em}}; doors blocked before reasons were required have no entry.
function blockReasons(key){try{return JSON.parse(state.settings[BLOCK_KEYS[key]+'_motivos']||'{}')}catch{return {}}}
function thirdPartyDoors(key){try{return new Set(JSON.parse(state.settings[THIRD_PARTY_KEYS[key]]||'[]'))}catch{return new Set()}}
function doorStatus(n,held,blocked){return held.has(n)?'ocupado':blocked.has(n)?'bloqueado':'livre'}
function freeDoors(key){const held=holders(key),blocked=blockedDoors(key);return doorNumbers(MAPS[key]).filter(n=>doorStatus(n,held,blocked)==='livre')}
function doorCounts(key){
  const held=holders(key),blocked=blockedDoors(key),counts={livre:0,ocupado:0,bloqueado:0};
  for(const n of doorNumbers(MAPS[key]))counts[doorStatus(n,held,blocked)]++;
  return counts;
}
const plural=(n,one,many)=>`${n} ${n===1?one:many}`;
const countsText=c=>`${plural(c.livre,'livre','livres')} · ${plural(c.ocupado,'ocupado','ocupados')} · ${plural(c.bloqueado,'bloqueado','bloqueados')}`;
const occupancy=key=>doorCounts(key).ocupado/doorCount(MAPS[key])*100;
const percent=value=>value.toLocaleString('pt-BR',{maximumFractionDigits:1})+'%';

// Options of the door selects in the record form: the free doors, plus the one this record already holds.
function doorOptions(doors,value,empty='Selecione…'){
  const saved=value===''||value==null?null:Number(value);
  const numbers=saved!==null&&!doors.includes(saved)?[...doors,saved].sort((a,b)=>a-b):doors;
  return `<option value="">${empty}</option>${numbers.map(n=>`<option value="${n}" ${n===saved?'selected':''}>${n}</option>`).join('')}`;
}
function doorInput(key,attrs,value){
  const options=key==='escaninho'?doorOptions(freeDoors('escaninhos'),value):doorOptions([],value,'Escolha o vestiário');
  return `<select ${attrs} data-saved="${esc(value)}">${options}</select>`;
}
// The locker list depends on the room chosen; the saved locker only belongs to the saved room.
function bindDoorForm(){
  const room=$('#f-vestiario'),door=$('#f-armario');if(!room||!door)return;
  const savedRoom=room.value,saved=door.dataset.saved;
  const fill=()=>{
    const doors=room.value?freeDoors(room.value.toLowerCase()):[];
    door.innerHTML=doorOptions(doors,room.value===savedRoom?saved:'',room.value?'Selecione…':'Escolha o vestiário');
  };
  room.addEventListener('change',fill);fill();
}

function mapPanel(){
  const m=MAPS[mapView.current];
  const tabs=Object.entries(MAPS).map(([key,t])=>`<button class="maptab ${key===mapView.current?'active':''}" role="tab" aria-selected="${key===mapView.current}" data-action="esc-tab" data-map="${key}">${esc(t.tab)}<small>${percent(occupancy(key))}</small></button>`).join('');
  return `<section class="panel escpanel"><div class="maptabs" role="tablist" aria-label="Escolha o mapa">${tabs}</div><div class="paneltitle"><div><h2>${esc(m.title)}</h2><p>Clique em uma porta para ver o cadastro, vincular um colaborador ou liberar o ${m.noun}.</p></div><div class="escstats"><div class="escocup" title="Portas ocupadas em relação ao total de ${doorCount(m)}"><span>Ocupação</span><strong id="esc-pct"></strong><div class="escbarra" aria-hidden="true"><i id="esc-bar"></i></div></div><span class="pill" id="esc-count"></span></div></div>
  <div class="escbar"><div class="esclegend"><span><i class="livre"></i>Livre</span><span><i class="ocupado"></i>Ocupado</span><span><i class="bloqueado"></i>Bloqueado</span><span><i class="terceirizado">T</i>Terceirizado</span></div>
  <div class="esctools"><input id="esc-go" type="number" min="${m.first}" max="${m.last}" step="1" inputmode="numeric" placeholder="Nº" aria-label="Número da porta para localizar"><button class="btn" data-action="esc-go">${icon('search')} Localizar</button>${isAdmin()?`<button class="btn" data-action="esc-seq">${icon('lock')} Bloquear sequência</button>`:''}
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

function thirdPartyBadge(door,m){
  const {x,y,w,h,font}=m.badge,tag=document.createElementNS(SVG_NS,'g'),box=document.createElementNS(SVG_NS,'rect'),text=document.createElementNS(SVG_NS,'text');
  tag.setAttribute('class','escterc');
  for(const [name,value] of Object.entries({x,y,width:w,height:h,rx:h/4}))box.setAttribute(name,value);
  for(const [name,value] of Object.entries({x:x+w/2,y:y+h/2,'font-size':font,'text-anchor':'middle','dominant-baseline':'central'}))text.setAttribute(name,value);
  text.textContent='TERC';tag.append(box,text);door.appendChild(tag);
}

function paintMap(){
  if(!$('#escmap svg'))return;
  const key=mapView.current,m=MAPS[key],held=holders(key),blocked=blockedDoors(key),reasons=blockReasons(key),thirdParty=thirdPartyDoors(key),Noun=capital(m.noun);
  for(const n of doorNumbers(m)){
    const door=document.getElementById(doorId(n));if(!door)continue;
    const status=doorStatus(n,held,blocked),r=held.get(n);
    door.dataset.status=status;
    door.toggleAttribute('data-terceirizado',thirdParty.has(n));
    door.querySelector('.escnome')?.remove();door.querySelector('.escterc')?.remove();
    const why=status==='bloqueado'&&reasons[n]?`: ${reasons[n].motivo}`:'';
    const third=thirdParty.has(n)?' · terceirizado':'';
    const label=(r?`${Noun} ${n}, ocupado por ${r.payload.nome}`:`${Noun} ${n}, ${status}${why}`)+third;
    door.setAttribute('aria-label',label);
    const title=door.querySelector('title');if(title)title.textContent=r?`${Noun} ${n} — ${r.payload.nome}${r.payload.setor?' ('+r.payload.setor+')':''}${openCopy(r)?' · cópia da chave em uso':''}${third}`:label;
    if(r)nameLabel(door,m,r.payload.nome);
    if(third)thirdPartyBadge(door,m);
  }
  const counts=doorCounts(key),rate=counts.ocupado/doorCount(m)*100;
  $('#esc-count').textContent=countsText(counts);
  $('#esc-pct').textContent=percent(rate);
  $('#esc-bar').style.width=rate+'%';
  for(const tab of document.querySelectorAll('.maptab'))tab.querySelector('small').textContent=percent(occupancy(tab.dataset.map));
}

// Both locker rooms share vestiario.svg: name the room shown in its heading and label.
function titleRoom(box,m){
  const room=m.vestiario,heading=[...box.querySelectorAll('svg text')].find(t=>t.textContent.startsWith('VESTIÁRIO'));
  if(heading)heading.textContent='VESTIÁRIO '+room.toUpperCase();
  box.querySelector('svg').setAttribute('aria-label',`Vestiário ${room.toLowerCase()}, armários ${m.first} a ${m.last}`);
}

// A room numbered from the middle of the drawing: drop the earlier sets and move the rest up to the first places.
function keepRoomRange(box,m){
  const svg=box.querySelector('svg'),towers=[...svg.querySelectorAll('g[id^="torre-"]')],places=towers.map(t=>t.getAttribute('transform'));
  const kept=towers.filter(t=>Number(t.querySelector('.armario').dataset.numero)>=m.first);
  towers.filter(t=>!kept.includes(t)).forEach(t=>t.remove());
  kept.forEach((t,i)=>t.setAttribute('transform',places[i]));
  const texts=[...svg.querySelectorAll('text')],starting=start=>texts.find(t=>t.textContent.startsWith(start));
  const number=n=>String(n).padStart(3,'0'),title=starting('Armários 0'),count=starting('300 ARMÁRIOS'),sets=starting('25 conjuntos'),footnote=starting('Numeração');
  if(title)title.textContent=`Armários ${number(m.first)} a ${number(m.last)}`;
  if(count)count.textContent=`${doorCount(m)} ARMÁRIOS`;
  if(sets)sets.textContent=`${kept.length} conjuntos de 12 portas`;
  // The next free place holds the note; the drawing ends right below it.
  const [x,y]=places[kept.length].match(/[\d.]+/g).map(Number),height=y+ROOM_NOTE_HEIGHT;
  if(count)count.parentElement.setAttribute('transform',`translate(${x} ${y})`);
  if(footnote)footnote.setAttribute('y',height-ROOM_FOOT_MARGIN);
  svg.querySelector('rect').setAttribute('height',height);
  svg.setAttribute('viewBox',`0 0 ${m.width} ${height}`);
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
  if(m.vestiario)titleRoom(box,m);
  if(m.first>1)keepRoomRange(box,m);
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
  const n=Number($('#esc-go').value),m=MAPS[mapView.current];
  if(!Number.isInteger(n)||n<m.first||n>m.last){toast(`Informe um número de ${m.first} a ${m.last}.`,true);return}
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
  const isThird=thirdPartyDoors(key).has(n),thirdNote=isThird?`<div class="notice terceiro">Este ${m.noun} pertence a um terceirizado.</div>`:'';
  const thirdButton=isAdmin()?`<button class="btn" data-action="esc-third" data-n="${n}" data-mark="${!isThird}">${icon('badge')} ${isThird?'Tirar marca de terceirizado':'Marcar como terceirizado'}</button>`:'';
  const status=doorStatus(n,holders(key),blockedDoors(key)),where=m.vestiario?` · vestiário ${m.vestiario.toLowerCase()}`:'';
  const close='<button class="btn" data-action="close">Fechar</button>';
  if(r){
    const fields=moduleBy('chaves').fields,rows=fields.filter(f=>r.payload[f[0]]).map(f=>`<div><small>${esc(f[1])}</small><p>${esc(f[2]==='datetime-local'?fmt(r.payload[f[0]]):r.payload[f[0]])}</p></div>`).join('');
    const others=otherLinks(r,key),note=others.length?`<div class="notice">Este cadastro também ocupa ${esc(others.join(' e '))}. Liberar encerra o cadastro inteiro e libera tudo.</div>`:'';
    const copy=openCopy(r),release=canReturn(r)&&!copy?`<button class="btn primary" data-action="return" data-id="${r.id}">${icon('return')} Liberar ${m.noun}</button>`:'';
    openModal(`${Noun} ${n} · ocupado`,'Cadastro vinculado a esta porta'+where+'.',`<div class="modalbody">${thirdNote}${note}${copy?`<div class="notice copyout">${copyLine(copy)}<br>Para liberar, registre antes a devolução da cópia.</div>`:''}<div class="detailgrid">${rows}<div><small>Cadastrado por</small><p>${esc(r.creator)} · ${fmt(r.created_at)}</p></div></div>${copyHistory(r)}</div>`,
      `<div class="modalfoot">${close}${thirdButton}<button class="btn" data-action="view" data-id="${r.id}">${icon('eye')} Registro completo</button>${copyButton(r)}${release}</div>`);
    return;
  }
  const blocked=status==='bloqueado';
  const text=blocked?`Este ${m.noun} está bloqueado pelo administrador e não aceita novos vínculos até ser desbloqueado.`:`Este ${m.noun} está livre e pode ser vinculado a um colaborador.`;
  const adminButton=isAdmin()?`<button class="btn" data-action="${blocked?'esc-unblock':'esc-block'}" data-n="${n}">${icon('lock')} ${blocked?'Desbloquear':'Bloquear'}</button>`:'';
  const reason=blockReasons(key)[n];
  const details=!blocked?'':reason?`<div class="detailgrid"><div class="wide"><small>Motivo do bloqueio</small><p>${esc(reason.motivo)}</p></div><div><small>Bloqueado por</small><p>${esc(reason.por)} · ${fmt(reason.em)}</p></div></div>`
    :'<div class="detailgrid"><div class="wide"><small>Motivo do bloqueio</small><p>Não informado (bloqueado antes de o motivo ser obrigatório).</p></div></div>';
  openModal(`${Noun} ${n} · ${status}`,'Situação atual da porta'+where+'.',`<div class="modalbody">${thirdNote}<div class="notice">${text}</div>${details}</div>`,
    `<div class="modalfoot">${close}${thirdButton}${adminButton}${blocked?'':`<button class="btn primary" data-action="esc-link" data-n="${n}">${icon('plus')} Vincular colaborador</button>`}</div>`);
}

// Spare keys: a copy handed to the person keeps the main record open until the copy comes back.
const COPY_REASONS=['Esqueceu a chave','Perdeu a chave','Outro'];
const openCopy=r=>(r.copias||[]).find(k=>!k.devolvida_em);
const copyLine=k=>`Cópia da chave entregue em ${fmt(k.entregue_em)} por ${esc(k.entregue_por)} · ${esc(k.motivo)}${k.observacao?` · ${esc(k.observacao)}`:''}`;
function copyHistory(r){
  const list=r.copias||[];if(!list.length)return '';
  const items=[...list].reverse().map(k=>`<li><span>${copyLine(k)}</span><small>${k.devolvida_em?`Devolvida em ${fmt(k.devolvida_em)} por ${esc(k.devolvida_por)}`:'<b>Em uso</b>'}</small></li>`).join('');
  return `<div class="copyhist"><small>Cópias da chave (${list.length})</small><ul>${items}</ul></div>`;
}
function copyButton(r){
  if(r.module!=='chaves'||r.status!=='Em aberto'||r.payload.devolucao)return '';
  const copy=openCopy(r);
  return copy?`<button class="btn primary" data-action="esc-copy-return" data-copy="${copy.id}">${icon('return')} Registrar devolução da cópia</button>`
    :`<button class="btn" data-action="esc-copy-give" data-id="${r.id}">${icon('plus')} Entregar cópia da chave</button>`;
}
function copyForm(rid){
  const r=state.records.find(x=>x.id===rid);
  openModal('Entregar cópia da chave',`${r.payload.nome} · o cadastro continua em aberto.`,
    `<div class="modalbody"><div class="field"><label for="f-copia-motivo">Motivo</label><select id="f-copia-motivo">${COPY_REASONS.map(x=>`<option>${esc(x)}</option>`).join('')}</select></div>
    <div class="field"><label for="f-copia-obs">Observação (opcional)</label><textarea id="f-copia-obs" maxlength="300" rows="2" placeholder="Ex.: devolve no fim do turno"></textarea></div></div>`,
    `<div class="modalfoot"><button class="btn" data-action="close">Cancelar</button><button class="btn primary" data-action="esc-copy-save" data-id="${rid}">${icon('plus')} Registrar entrega</button></div>`);
}

function blockForm(n){
  const m=MAPS[mapView.current],where=m.vestiario?` · vestiário ${m.vestiario.toLowerCase()}`:'';
  openModal(`Bloquear ${m.noun} ${n}`,'Informe por que esta porta vai ficar bloqueada'+where+'.',
    `<div class="modalbody"><div class="field"><label for="f-motivo">Motivo do bloqueio</label><textarea id="f-motivo" maxlength="200" rows="3" required placeholder="Ex.: fechadura quebrada, aguardando manutenção"></textarea></div></div>`,
    `<div class="modalfoot"><button class="btn" data-action="close">Cancelar</button><button class="btn primary" data-action="esc-block-save" data-n="${n}">${icon('lock')} Bloquear</button></div>`);
}

function sequenceForm(){
  const m=MAPS[mapView.current],where=m.vestiario?` do vestiário ${m.vestiario.toLowerCase()}`:'',range=`min="${m.first}" max="${m.last}" step="1" inputmode="numeric" required`;
  openModal('Bloquear ou desbloquear sequência',`Vale para os ${m.noun}s${where}, de ${m.first} a ${m.last}.`,
    `<div class="modalbody"><div class="formgrid"><div class="field"><label for="f-seq-de">Do número</label><input id="f-seq-de" type="number" ${range}></div><div class="field"><label for="f-seq-ate">Até o número</label><input id="f-seq-ate" type="number" ${range}></div></div>
    <div class="field seqmotivo"><label for="f-motivo">Motivo do bloqueio</label><textarea id="f-motivo" maxlength="200" rows="3" placeholder="Ex.: reforma do vestiário"></textarea><small class="basehint">Obrigatório para bloquear. Para desbloquear, não precisa.</small></div>
    <p class="formmeta">Portas ocupadas ficam de fora: libere-as antes. Portas já bloqueadas mantêm o motivo que já tinham.</p></div>`,
    `<div class="modalfoot"><button class="btn" data-action="close">Cancelar</button><button class="btn" data-action="esc-seq-unblock">${icon('lock')} Desbloquear sequência</button><button class="btn primary" data-action="esc-seq-block">${icon('lock')} Bloquear sequência</button></div>`);
}

// 40, 41, 42, 50 becomes "40 a 42, 50".
function doorList(numbers){
  const parts=[];
  for(const n of numbers){const last=parts[parts.length-1];if(last&&last[1]===n-1)last[1]=n;else parts.push([n,n])}
  return parts.map(([a,b])=>a===b?String(a):`${a} a ${b}`).join(', ');
}
function sequenceResult(result,blocking,m){
  const nouns=m.noun+'s',done=result.alterados.length,verb=blocking?'bloqueado':'desbloqueado';
  const parts=[done?plural(done,`${m.noun} ${verb}`,`${nouns} ${verb}s`):`Nenhum ${m.noun} ${verb}`];
  if(result.ocupados.length)parts.push(`ocupados, ficaram de fora: ${doorList(result.ocupados)}`);
  if(result.ja_estavam.length)parts.push(`${blocking?'já estavam bloqueados':'não estavam bloqueados'}: ${doorList(result.ja_estavam)}`);
  return parts.join(' · ')+'.';
}
async function saveSequence(blocking,key,m){
  const de=Number($('#f-seq-de').value),ate=Number($('#f-seq-ate').value),motivo=$('#f-motivo').value.trim();
  const inRange=n=>Number.isInteger(n)&&n>=m.first&&n<=m.last;
  if(!inRange(de)||!inRange(ate)){toast(`Informe números de ${m.first} a ${m.last}.`,true);return}
  if(de>ate){toast('O número inicial não pode ser maior que o final.',true);return}
  if(blocking&&!motivo){toast('Informe o motivo do bloqueio.',true);$('#f-motivo').focus();return}
  const result=await api('mapas/bloqueio-sequencia',{method:'POST',body:JSON.stringify({mapa:key,de,ate,bloqueado:blocking,...(blocking?{motivo}:{})})});
  $('#modal').close();await refreshMap();toast(sequenceResult(result,blocking,m),!result.alterados.length);
}

async function refreshMap(){await loadData();paintMap();const table=$('#record-table');if(table)table.innerHTML=recordTable()}

document.addEventListener('click',async e=>{
  const button=e.target.closest('[data-action^="esc-"]');if(!button)return;
  const action=button.dataset.action,n=Number(button.dataset.n),key=mapView.current,m=MAPS[key];
  try{
    switch(action){
      case 'esc-tab':if(button.dataset.map!==key){mapView.current=button.dataset.map;render()}break;
      case 'esc-link':$('#modal').close();recordForm(null,'chaves',m.vestiario?{vestiario:m.vestiario,armario:String(n)}:{escaninho:String(n)});break;
      case 'esc-block':$('#modal').close();blockForm(n);break;
      case 'esc-block-save':case 'esc-unblock':{
        const blocking=action==='esc-block-save',motivo=blocking?$('#f-motivo').value.trim():'';
        if(blocking&&!motivo){toast('Informe o motivo do bloqueio.',true);$('#f-motivo').focus();break}
        button.disabled=true;
        await api('mapas/bloqueio',{method:'POST',body:JSON.stringify({mapa:key,numero:n,bloqueado:blocking,...(blocking?{motivo}:{})})});
        $('#modal').close();await refreshMap();toast(`${capital(m.noun)} ${n} ${blocking?'bloqueado':'desbloqueado'}.`);break}
      case 'esc-seq':sequenceForm();break;
      case 'esc-seq-block':case 'esc-seq-unblock':
        button.disabled=true;
        await saveSequence(action==='esc-seq-block',key,m);
        button.disabled=false;break;
      case 'esc-third':{
        const marking=button.dataset.mark==='true';
        button.disabled=true;
        await api('mapas/terceirizado',{method:'POST',body:JSON.stringify({mapa:key,numero:n,terceirizado:marking})});
        $('#modal').close();await refreshMap();toast(`${capital(m.noun)} ${n} ${marking?'marcado como terceirizado':'sem a marca de terceirizado'}.`);break}
      case 'esc-copy-give':$('#modal').close();copyForm(Number(button.dataset.id));break;
      case 'esc-copy-save':
        button.disabled=true;
        await api(`records/${button.dataset.id}/copias`,{method:'POST',body:JSON.stringify({motivo:$('#f-copia-motivo').value,observacao:$('#f-copia-obs').value.trim()})});
        $('#modal').close();await refreshMap();toast('Cópia da chave entregue. O cadastro continua em aberto.');break;
      case 'esc-copy-return':
        button.disabled=true;
        await api(`copias/${button.dataset.copy}/devolucao`,{method:'POST',body:'{}'});
        $('#modal').close();await refreshMap();toast('Devolução da cópia registrada. O cadastro continua em aberto.');break;
      case 'esc-go':goToDoor();break;
      case 'esc-zoomin':stepZoom(1);break;
      case 'esc-zoomout':stepZoom(-1);break;
      case 'esc-fit':applyZoom(fitZoom(),false);break;
    }
  }catch(err){toast(err.message,true);button.disabled=false}
});
