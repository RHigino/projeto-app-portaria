'use strict';
// Bases imported from .xlsx (Configurações) and the lookups they power in the record forms.
const BASES_INFO=[
  ['colaboradores','Colaboradores','Situação, Matricula, Nome Completo, Cargo','Pela matrícula, preenche nome e cargo em Armários e Escaninhos, Saída de materiais e Equipamentos móveis.'],
  ['terceirizados','Terceirizados','Nome, CPF, RG, Empresa/Transportadora','Pelo CPF ou RG, preenche nome e empresa no Cadastro de pessoas.'],
  ['fornecedores','Fornecedores','Transportador, Fornecedor, Motivo','Listas para escolher em Devoluções.'],
];
const COLABORADOR_MODULES=['chaves','materiais','equipamentos'];
const LIST_FIELDS=['transportador','fornecedor','motivo'];
const LOOKUP_DELAY=300;  // ms after the last keystroke
const XLSX_TYPE='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const XLSX_MAX=10*1024*1024;

function basesPanel(){
  return `<section class="panel" id="bases-panel"><h2>Bases de dados (.xlsx)</h2><p>Importe as planilhas para preencher os cadastros automaticamente.</p>${BASES_INFO.map(([key,name,columns,use])=>`<div class="baserow"><div><strong>${name}</strong><small>${use}</small><small>Colunas: ${columns}</small><small class="baseinfo" id="base-info-${key}">Carregando…</small></div><button class="btn" data-action="base-import" data-base="${key}">${icon('upload')} Importar .xlsx</button></div>`).join('')}<input type="file" id="basefile" accept=".xlsx,${XLSX_TYPE}" hidden><p class="formmeta">Reimportar atualiza quem já existe (matrícula, CPF/RG ou valor) e acrescenta os novos; nada é apagado. Datas de admissão e nascimento e Gestor não são gravados.</p></section>`;
}

const when=value=>value?' · atualizado em '+fmt(value):'';
async function mountBases(){
  if(!$('#bases-panel'))return;
  const input=$('#basefile');
  input.onchange=()=>uploadBase(input);
  try{
    const s=await api('bases');
    $('#base-info-colaboradores').textContent=s.colaboradores.total?`${s.colaboradores.total} colaboradores${when(s.colaboradores.atualizado)}`:'Nenhuma planilha importada.';
    $('#base-info-terceirizados').textContent=s.terceirizados.total?`${s.terceirizados.total} terceirizados${when(s.terceirizados.atualizado)}`:'Nenhuma planilha importada.';
    const f=s.fornecedores;$('#base-info-fornecedores').textContent=f.transportador+f.fornecedor+f.motivo?`${f.transportador} transportadores · ${f.fornecedor} fornecedores · ${f.motivo} motivos`:'Nenhuma planilha importada.';
  }catch(err){for(const el of document.querySelectorAll('.baseinfo'))el.textContent='Não foi possível consultar as bases: '+err.message}
}

async function uploadBase(input){
  const file=input.files[0],base=input.dataset.base,name=BASES_INFO.find(b=>b[0]===base)[1];
  input.value='';
  if(!file)return;
  try{
    if(!file.name.toLowerCase().endsWith('.xlsx'))throw new Error('Escolha um arquivo .xlsx (Pasta de Trabalho do Excel).');
    if(file.size>XLSX_MAX)throw new Error('Arquivo maior que 10 MB. Divida a planilha.');
    toast(`Importando ${name}…`);
    const res=await fetch('/api/bases/'+base,{method:'POST',headers:{'Content-Type':XLSX_TYPE,'X-CSRF-Token':state.user.csrf},body:file});
    const data=await res.json();
    if(!res.ok)throw new Error(data.error||'Falha na importação.');
    await loadData();await mountBases();
    toast(`${name}: ${data.novos} novos, ${data.atualizados} atualizados${data.ignorados?`, ${data.ignorados} linhas ignoradas sem dados obrigatórios`:''}.`);
  }catch(err){toast(err.message,true)}
}

document.addEventListener('click',e=>{
  const button=e.target.closest('[data-action="base-import"]');if(!button)return;
  const input=$('#basefile');input.dataset.base=button.dataset.base;input.click();
});

// ---- Form lookups ----
function debounce(fn){let timer;return (...args)=>{clearTimeout(timer);timer=setTimeout(()=>fn(...args),LOOKUP_DELAY)}}
function setHint(input,text,warn=false){
  let el=input.parentElement.querySelector('.basehint');
  if(!el){el=document.createElement('small');el.className='basehint';input.parentElement.appendChild(el)}
  el.textContent=text;el.classList.toggle('warn',warn);
}
// Fills only empty fields or values the lookup itself put there, never what the user typed.
function fillIn(input,value){if(input&&value&&(!input.value||input.dataset.auto==='1')){input.value=value;input.dataset.auto='1'}}
function markTyped(...inputs){for(const input of inputs)input?.addEventListener('input',e=>{if(e.isTrusted)input.dataset.auto=''})}
function attachList(input,options){
  const list=document.createElement('datalist');list.id='dl-'+input.id;input.after(list);input.setAttribute('list',list.id);
  setOptions(list,options);return list;
}
function setOptions(list,options){list.replaceChildren(...options.map(([value,label])=>{const o=document.createElement('option');o.value=value;if(label)o.label=label;return o}))}
async function lookup(input,request,onResult){
  try{onResult(await api(request))}catch(err){setHint(input,'Não foi possível consultar a base: '+err.message,true)}
}

function bindColaborador(form){
  const mat=form.querySelector('#f-matricula'),nome=form.querySelector('#f-nome'),cargo=form.querySelector('#f-cargo');
  const list=attachList(nome,[]);let options=[];
  markTyped(mat,nome,cargo);
  const apply=p=>{
    fillIn(nome,p.nome);fillIn(cargo,p.cargo);fillIn(mat,p.matricula);
    const away=Boolean(p.situacao)&&!p.situacao.startsWith('ATIV');
    setHint(mat,`Base: ${p.nome}${p.cargo?' · '+p.cargo:''}${p.situacao?' · '+p.situacao:''}${away?' — confira antes de vincular':''}`,away);
  };
  mat.addEventListener('input',debounce(()=>{
    const q=mat.value.trim();if(q.length<2){setHint(mat,'');return}
    lookup(mat,'bases/colaboradores?q='+encodeURIComponent(q),found=>{
      const p=found.find(x=>x.matricula===q.replace(/^0+/,'')||x.matricula===q);
      if(p)apply(p);else setHint(mat,'Matrícula não encontrada na base. Preencha os dados manualmente.');
    });
  }));
  nome.addEventListener('input',debounce(()=>{
    const q=nome.value.trim().toUpperCase(),picked=options.find(p=>p.nome===q);
    if(picked){apply(picked);return}
    if(q.length<2)return;
    lookup(nome,'bases/colaboradores?q='+encodeURIComponent(q),found=>{options=found;setOptions(list,found.map(p=>[p.nome,`${p.matricula}${p.cargo?' · '+p.cargo:''}`]))});
  }));
}

function bindTerceiro(form){
  const doc=form.querySelector('#f-documento'),nome=form.querySelector('#f-nome'),empresa=form.querySelector('#f-empresa');
  const list=attachList(nome,[]);let options=[];
  markTyped(nome,empresa);
  doc.addEventListener('input',debounce(()=>{
    const q=doc.value.trim();if(q.replace(/[^0-9a-z]/gi,'').length<4){setHint(doc,'');return}
    lookup(doc,'bases/terceirizados?documento='+encodeURIComponent(q),({pessoa})=>{
      if(!pessoa){setHint(doc,'Documento não encontrado na base de terceirizados.');return}
      fillIn(nome,pessoa.nome);fillIn(empresa,pessoa.empresa);setHint(doc,`Base: ${pessoa.nome}${pessoa.empresa?' · '+pessoa.empresa:''}`);
    });
  }));
  nome.addEventListener('input',debounce(()=>{
    const q=nome.value.trim().toUpperCase(),picked=options.find(p=>p.nome===q);
    if(picked){fillIn(empresa,picked.empresa);return}
    if(q.length<2)return;
    lookup(nome,'bases/terceirizados?q='+encodeURIComponent(q),found=>{options=found;setOptions(list,found.map(p=>[p.nome,p.empresa]))});
  }));
}

function bindBaseLookups(moduleId){
  const form=$('#recordform');if(!form)return;
  if(COLABORADOR_MODULES.includes(moduleId)&&form.querySelector('#f-matricula')&&form.querySelector('#f-nome'))bindColaborador(form);
  if(moduleId==='pessoas')bindTerceiro(form);
  if(moduleId==='devolucoes')for(const key of LIST_FIELDS){const input=form.querySelector('#f-'+key);if(input)attachList(input,(state.listas?.[key]||[]).map(v=>[v]))}
}
