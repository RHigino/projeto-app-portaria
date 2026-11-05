'use strict';
// Bases imported from .xlsx (Configurações) and the lookups they power in the record forms.
const BASES_INFO=[
  ['colaboradores','Colaboradores','Aba Colaboradores','Situação, Matricula, Nome Completo, Cargo','Pela matrícula, preenche nome e cargo em Armários e Escaninhos, Saída de materiais e Equipamentos móveis.'],
  ['terceirizados','Terceirizados','Aba Acesso de Terceiros','Nome, CPF, RG, Empresa/Transportadora','Pelo CPF ou RG, preenche nome e empresa no Cadastro de pessoas.'],
  ['fornecedores','Fornecedores','Aba Fornecedores','Transportador, Fornecedor, Motivo','Listas para escolher em Devoluções.'],
  ['frota','Placas e condutores','Aba Placa do carro e caminhão','Placas dos Caminhoes, Placa do Carro, Condutor, Auxiliar, Rota','Listas para escolher em Rotas (rota, placa do caminhão, condutor e auxiliar) e em Veículos (placa do carro e motorista).'],
];
const COLABORADOR_MODULES=['chaves','materiais','equipamentos'];
// Form field -> choice list imported from the workbook, by module. Shown as a regular select.
const MODULE_SELECTS={
  devolucoes:{transportador:'transportador',fornecedor:'fornecedor',motivo:'motivo'},
  rotas:{rota:'rota',placa:'placa_caminhao',condutor:'condutor',auxiliar:'auxiliar'},
  veiculos:{placa:'placa_carro',motorista:'condutor'},
};
const LOOKUP_DELAY=300;  // ms after the last keystroke
const XLSX_TYPE='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const XLSX_MAX=10*1024*1024;

function basesPanel(){
  return `<section class="panel" id="bases-panel"><h2>Bases de dados (.xlsx)</h2><p>Importe uma única planilha, com uma aba para cada base. Só as abas presentes no arquivo são atualizadas.</p><button class="btn" data-action="base-import">${icon('upload')} Importar planilha .xlsx</button><p class="baseinfo" id="base-result" role="status"></p>${BASES_INFO.map(([key,name,tab,columns,use])=>`<div class="baserow"><div><strong>${name}</strong><small>${tab} · Colunas: ${columns}</small><small>${use}</small><small class="baseinfo" id="base-info-${key}">Carregando…</small></div></div>`).join('')}<input type="file" id="basefile" accept=".xlsx,${XLSX_TYPE}" hidden><p class="formmeta">Reimportar atualiza quem já existe (matrícula, CPF/RG ou valor) e acrescenta os novos; nada é apagado. Datas de admissão e nascimento e Gestor não são gravados. Placas inválidas ficam fora das listas.</p></section>`;
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
    const v=s.frota;$('#base-info-frota').textContent=v.rota+v.placa_caminhao+v.placa_carro+v.condutor+v.auxiliar?`${v.rota} rotas · ${v.placa_caminhao} placas de caminhão · ${v.placa_carro} placas de carro · ${v.condutor} condutores · ${v.auxiliar} auxiliares`:'Nenhuma planilha importada.';
  }catch(err){for(const el of document.querySelectorAll('.baserow .baseinfo'))el.textContent='Não foi possível consultar as bases: '+err.message}
}

function importSummary({abas,ignoradas}){
  const tabs=BASES_INFO.filter(([key])=>abas[key]).map(([key,name])=>{
    const n=abas[key];return `${name}: ${n.novos} novos, ${n.atualizados} já existentes${n.ignorados?`, ${n.ignorados} ignorados`:''}`;
  });
  return tabs.join(' · ')+(ignoradas.length?` · Abas não usadas: ${ignoradas.join(', ')}`:'');
}

async function uploadBase(input){
  const file=input.files[0],result=$('#base-result');
  input.value='';
  if(!file)return;
  result.textContent='';
  try{
    if(!file.name.toLowerCase().endsWith('.xlsx'))throw new Error('Escolha um arquivo .xlsx (Pasta de Trabalho do Excel).');
    if(file.size>XLSX_MAX)throw new Error('Arquivo maior que 10 MB. Divida a planilha.');
    toast('Importando planilha…');
    const res=await fetch('/api/bases',{method:'POST',headers:{'Content-Type':XLSX_TYPE,'X-CSRF-Token':state.user.csrf},body:file});
    const data=await res.json();
    if(!res.ok)throw new Error(data.error||'Falha na importação.');
    await loadData();await mountBases();
    result.textContent=importSummary(data);
    toast('Planilha importada.');
  }catch(err){result.textContent=err.message;toast(err.message,true)}
}

document.addEventListener('click',e=>{
  if(e.target.closest('[data-action="base-import"]'))$('#basefile').click();
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
// Search-as-you-type panel for names, too many for a select. Drawn like the open list of a select.
function attachSuggest(input){
  const box=document.createElement('div');
  box.className='suggest';box.id='sg-'+input.id;box.hidden=true;box.setAttribute('role','listbox');
  input.after(box);
  input.setAttribute('role','combobox');input.setAttribute('aria-controls',box.id);input.setAttribute('aria-expanded','false');
  let active=-1;
  const mark=index=>{
    active=index;
    [...box.children].forEach((el,i)=>{el.classList.toggle('active',i===index);el.setAttribute('aria-selected',String(i===index))});
    box.children[index]?.scrollIntoView({block:'nearest'});
  };
  const hide=()=>{box.hidden=true;active=-1;input.setAttribute('aria-expanded','false')};
  const pick=value=>{input.value=value;hide();input.dispatchEvent(new Event('input',{bubbles:true}))};
  const option=([value,detail],index)=>{
    const el=document.createElement('div');
    el.className='suggestitem';el.setAttribute('role','option');el.textContent=value;
    if(detail){const small=document.createElement('small');small.textContent=detail;el.append(small)}
    el.addEventListener('mousedown',e=>{e.preventDefault();pick(value)});
    el.addEventListener('mousemove',()=>mark(index));
    return el;
  };
  const show=options=>{
    box.replaceChildren(...options.map(option));
    if(!options.length||document.activeElement!==input){hide();return}
    box.style.top=`${input.offsetTop+input.offsetHeight}px`;box.style.left=`${input.offsetLeft}px`;box.style.width=`${input.offsetWidth}px`;
    box.hidden=false;active=-1;input.setAttribute('aria-expanded','true');
  };
  input.addEventListener('blur',hide);
  input.addEventListener('keydown',e=>{
    if(box.hidden)return;
    const total=box.children.length;
    if(e.key==='ArrowDown'){e.preventDefault();mark((active+1)%total)}
    else if(e.key==='ArrowUp'){e.preventDefault();mark((active-1+total)%total)}
    else if(e.key==='Escape'){e.preventDefault();hide()}
    else if(e.key==='Enter'&&active>=0){e.preventDefault();pick(box.children[active].firstChild.textContent)}
  });
  return {show,hide};
}
// Swaps a text input for a select with the list. With no list imported yet, the input stays.
// A saved value outside the list stays available when editing.
function attachSelect(input,options){
  if(!options.length)return;
  const select=document.createElement('select');
  select.id=input.id;select.name=input.name;select.required=input.required;
  const values=input.value&&!options.includes(input.value)?[input.value,...options]:options;
  select.replaceChildren(...[['','Selecione…'],...values.map(v=>[v,v])].map(([value,label])=>{const o=document.createElement('option');o.value=value;o.textContent=label;return o}));
  select.value=input.value;
  input.replaceWith(select);
}
async function lookup(input,request,onResult){
  try{onResult(await api(request))}catch(err){setHint(input,'Não foi possível consultar a base: '+err.message,true)}
}

function bindColaborador(form){
  const mat=form.querySelector('#f-matricula'),nome=form.querySelector('#f-nome'),cargo=form.querySelector('#f-cargo');
  const list=attachSuggest(nome);let options=[];
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
    if(picked){list.hide();apply(picked);return}
    if(q.length<2){list.hide();return}
    lookup(nome,'bases/colaboradores?q='+encodeURIComponent(q),found=>{options=found;list.show(found.map(p=>[p.nome,`${p.matricula}${p.cargo?' · '+p.cargo:''}`]))});
  }));
}

function bindTerceiro(form){
  const doc=form.querySelector('#f-documento'),nome=form.querySelector('#f-nome'),empresa=form.querySelector('#f-empresa');
  const list=attachSuggest(nome);let options=[];
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
    if(picked){list.hide();fillIn(empresa,picked.empresa);return}
    if(q.length<2){list.hide();return}
    lookup(nome,'bases/terceirizados?q='+encodeURIComponent(q),found=>{options=found;list.show(found.map(p=>[p.nome,p.empresa]))});
  }));
}

function bindBaseLookups(moduleId){
  const form=$('#recordform');if(!form)return;
  if(COLABORADOR_MODULES.includes(moduleId)&&form.querySelector('#f-matricula')&&form.querySelector('#f-nome'))bindColaborador(form);
  if(moduleId==='pessoas')bindTerceiro(form);
  for(const [field,list] of Object.entries(MODULE_SELECTS[moduleId]||{})){
    const input=form.querySelector('#f-'+field);
    if(input)attachSelect(input,state.listas?.[list]||[]);
  }
}
