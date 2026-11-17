'use strict';
// Chaves de setores: one key per sector, taken and returned like a locker key, controlled in a table (no drawing).
const SECTOR_MODULE='chaves_setores';
const SECTOR_BLOCK_KEY='chaves_setores_bloqueadas';  // settings: {sector: {motivo, por, em}}
const SECTOR_STATUS={livre:['Livre','free'],uso:['Em uso','red'],bloqueada:['Bloqueada','warn']};

const sectorNames=()=>moduleBy(SECTOR_MODULE).fields.find(f=>f[0]==='setor')[4];
function blockedSectors(){try{return JSON.parse(state.settings[SECTOR_BLOCK_KEY]||'{}')}catch{return {}}}
const sectorHolder=sector=>state.records.find(r=>r.module===SECTOR_MODULE&&r.status==='Em aberto'&&!r.payload.devolucao&&r.payload.setor===sector);
function sectorState(sector,blocked){
  const holder=sectorHolder(sector);
  return {sector,holder,block:blocked[sector],status:holder?'uso':blocked[sector]?'bloqueada':'livre'};
}

function sectorRow({sector,holder,block,status}){
  const [label,tone]=SECTOR_STATUS[status];
  const who=holder?`<strong>${esc(holder.payload.nome)}</strong><small>Matrícula ${esc(holder.payload.matricula||'—')}</small>`
    :block?`<strong>${esc(block.motivo||'Sem motivo informado')}</strong><small>Bloqueada por ${esc(block.por||'—')} · ${fmt(block.em)}</small>`:'<small>—</small>';
  const actions=[
    status==='livre'?`<button class="btn primary" data-action="sk-take" data-setor="${esc(sector)}">${icon('key')} Entregar chave</button>`:'',
    status==='uso'?`<button class="btn" data-action="sk-return" data-id="${holder.id}">${icon('check')} Registrar devolução</button>`:'',
    isAdmin()&&status==='livre'?`<button class="btn" data-action="sk-block" data-setor="${esc(sector)}">${icon('lock')} Bloquear</button>`:'',
    isAdmin()&&status==='bloqueada'?`<button class="btn" data-action="sk-unblock" data-setor="${esc(sector)}">Desbloquear</button>`:'',
  ].join('');
  return `<tr><td><strong>${esc(sector)}</strong></td><td><span class="badge ${tone}"><span class="dot"></span>${label}</span></td><td>${who}</td><td>${holder?fmt(holder.payload.retirada):'—'}</td><td><div class="buttons sectoractions">${actions}</div></td></tr>`;
}

function sectorKeysPanel(){
  const blocked=blockedSectors(),rows=sectorNames().map(s=>sectorState(s,blocked));
  const count=status=>rows.filter(r=>r.status===status).length;
  const summary=`${plural(count('livre'),'livre','livres')} · ${count('uso')} em uso · ${plural(count('bloqueada'),'bloqueada','bloqueadas')}`;
  return `<section class="panel sectorpanel"><div class="paneltitle"><div><h2>Chaves dos setores</h2><p>Cada setor tem uma chave. Entregue a chave pela matrícula e registre a devolução quando ela voltar.</p></div><span class="pill">${summary}</span></div><div class="tablewrap"><table><thead><tr><th>Setor</th><th>Situação</th><th>Com quem / motivo</th><th>Retirada</th><th>Ações</th></tr></thead><tbody>${rows.map(sectorRow).join('')}</tbody></table></div></section>`;
}

function sectorBlockForm(sector){
  openModal(`Bloquear a chave de ${sector}`,'Informe por que esta chave vai ficar bloqueada.',
    `<div class="modalbody"><div class="field"><label for="f-motivo">Motivo do bloqueio</label><textarea id="f-motivo" maxlength="200" rows="3" required placeholder="Ex.: fechadura trocada, chave perdida"></textarea></div></div>`,
    `<div class="modalfoot"><button class="btn" data-action="close">Cancelar</button><button class="btn primary" data-action="sk-block-save" data-setor="${esc(sector)}">${icon('lock')} Bloquear</button></div>`);
}

async function saveSectorBlock(button,sector,blocking){
  const motivo=blocking?$('#f-motivo').value.trim():'';
  if(blocking&&!motivo){toast('Informe o motivo do bloqueio.',true);$('#f-motivo').focus();return}
  button.disabled=true;
  try{
    await api('chaves-setores/bloqueio',{method:'POST',body:JSON.stringify({setor:sector,bloqueado:blocking,...(blocking?{motivo}:{})})});
    if(blocking)$('#modal').close();
    await loadData();render();toast(`Chave de ${sector} ${blocking?'bloqueada':'desbloqueada'}.`);
  }catch(err){toast(err.message,true)}finally{button.disabled=false}
}

document.addEventListener('click',e=>{
  const button=e.target.closest('[data-action^="sk-"]');
  if(!button)return;
  const sector=button.dataset.setor;
  switch(button.dataset.action){
    case 'sk-take':recordForm(null,SECTOR_MODULE,{setor:sector});break;
    case 'sk-return':returnForm(Number(button.dataset.id));break;
    case 'sk-block':sectorBlockForm(sector);break;
    case 'sk-block-save':saveSectorBlock(button,sector,true);break;
    case 'sk-unblock':saveSectorBlock(button,sector,false);break;
  }
});
