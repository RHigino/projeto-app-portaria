# Histórico de alterações

Registro das mudanças feitas no sistema Prevenção de Perdas (GateFlow), da mais recente para a mais antiga.

## Situação atual (30/10/2026)

- O projeto está em `Documents\projetospython\projeto-portariaprevencao\GateFlow`. Antes, ficava em `Downloads\GateFlow_Portaria_v1\GateFlow`.
- O sistema ainda está em testes locais, antes de ser divulgado.
- Os testes automáticos passam: `python -m unittest` (17 testes).
- **O `PrevencaoPerdas.exe` ainda não foi gerado com as mudanças de 29 e 30/10.** Gere de novo com `gerar_exe.bat` antes de levar para os computadores.

### Próximos passos combinados

1. Gerar o `.exe` atualizado e testar com o banco na pasta de rede do CD.

### Decisões registradas

- **Reset do banco: não fazer por enquanto.** O banco tinha 48 KB, e o SQLite aguenta milhões de registros. Se um dia crescer, a ideia é arquivar só os registros concluídos antigos (com backup antes), sem apagar a auditoria nem os vínculos ativos.

---

## 30/10/2026: textos em MAIÚSCULAS

- Todo texto dos cadastros (campos de texto e Observações) é gravado em **MAIÚSCULAS** pelo servidor, venha da tela ou da importação. Exemplo: "maria josé" vira "MARIA JOSÉ".
- Nos formulários de cadastro e de retorno, os campos de texto já aparecem em maiúsculas enquanto se digita.
- **Ficam como estão:**
  - Login e senha, porque a senha não pode ser alterada.
  - Listas de opção, como Masculino/Feminino e Regular/Extra.
  - Datas e números.
  - A busca, que já ignora maiúsculas e minúsculas.
- Os registros que já existiam foram convertidos uma única vez, ao iniciar. A chave `texto_maiusculo` em `settings` marca que a conversão já foi feita.
- Novo teste: `test_text_fields_saved_uppercase`.

## 30/10/2026: planta do CD na Visão geral

- O desenho do galpão no painel "Uma portaria mais inteligente" foi trocado pela **planta animada do CD Bahia** (`CD_Bahia_Layout_Animado.svg`): ruas, almoxarifado, alimentos e docas, com fluxos, sinais e empilhadeira animados.
- A cópia usada pela tela é `static/layout_cd.svg`. Ela entra como imagem (`<img>`): as animações rodam e o desenho não executa nada na página. Quem tem a opção de reduzir movimento no sistema operacional vê o desenho parado.
- **Tamanho:** a área do desenho passou de 280 para 380 px de largura (270 px em telas menores). No celular, o desenho continua escondido.

## 30/10/2026: bases importadas por planilha (.xlsx)

Em **Configurações > Bases de dados (.xlsx)**, o administrador importa três planilhas, sempre em `.xlsx`. As bases ficam **dentro do banco**, e não como arquivo solto na pasta de rede:
- O Excel não trava o arquivo.
- Só o administrador atualiza, e fica na auditoria.
- CPF e RG não ficam expostos numa pasta.

| Base | Colunas lidas | Uso no sistema |
|---|---|---|
| Colaboradores | Situação, Matricula, Nome Completo, Cargo | Em Armários e Escaninhos, Saída de materiais e Equipamentos móveis, a matrícula preenche nome e cargo. Digitar o nome sugere da base e preenche matrícula e cargo. Situação diferente de ATIVO mostra um aviso em laranja ("confira antes de vincular"). |
| Terceirizados | Nome, CPF, RG, Empresa/Transportadora | No Cadastro de pessoas, o CPF ou o RG digitado em Documento preenche nome e empresa. O nome também sugere da base. |
| Fornecedores | Transportador, Fornecedor, Motivo | Em Devoluções, os três campos viram listas para escolher, filtrando ao digitar e aceitando valor novo. Cada coluna é uma lista própria. |

**Regras da importação:**
- O cabeçalho pode estar abaixo de linhas de título; o sistema procura nas 20 primeiras linhas. Maiúsculas, acentos e espaços nos cabeçalhos não importam.
- **Não são gravadas:** Data da Admissão, Data do Nascimento e Gestor (LGPD: nenhum formulário usa).
- **Reimportar** atualiza quem já existe (pela matrícula, pelo CPF/RG ou pelo valor da lista) e acrescenta os novos. **Nada é apagado.**
- CPF digitado como número no Excel perde o zero da frente; o sistema recoloca. A busca por CPF ou RG ignora pontos e traços.
- Planilha errada (sem as colunas esperadas, ou sem nenhuma linha válida) é recusada com mensagem clara.
- Linhas sem os dados obrigatórios são contadas como "ignoradas": colaborador sem matrícula ou nome, terceirizado sem nome ou sem documento.
- Limites: 10 MB por arquivo e 20.000 linhas.
- **Privacidade:** a busca por nome de terceirizados não devolve CPF nem RG; o documento só serve para a busca exata.
- Os dados da base são gravados em MAIÚSCULAS.

**Arquivos:**
- Novos: `bases.py` (leitura do `.xlsx` só com a biblioteca padrão do Python, importação e buscas) e `static/bases.js` (painel de importação e preenchimento automático nos formulários).
- Tabelas novas no banco: `base_colaboradores`, `base_terceiros` e `base_listas`.
- Endereços:
  - `POST /api/bases/<colaboradores|terceirizados|fornecedores>` e `GET /api/bases`: só administrador.
  - `GET /api/bases/colaboradores?q=` e `GET /api/bases/terceirizados?documento=` ou `?q=`: qualquer usuário logado.
- Novos testes: `test_spreadsheet_bases` e `test_spreadsheet_saved_by_excel_library`. Este último usa o `openpyxl`, se estiver instalado.
- As planilhas reais **não** devem ficar na pasta do projeto.

## 30/10/2026: armários dos vestiários e troca de senha pelo administrador

### Redefinir senha pelo administrador

- Em **Usuários e permissões**, cada linha tem o botão de chave **Redefinir senha**. Ele pede a nova senha duas vezes, com mínimo de 10 caracteres.
- O usuário é desconectado e passa a entrar com a nova senha. Perfil e abas liberadas não mudam.
- O `redefinir_senha.bat` (CMD) continua existindo para quando nenhum administrador consegue entrar.

### Mapa dos armários (masculino e feminino)

**Filtro no topo do mapa:**
- A aba Armários e Escaninhos tem o filtro **Escaninhos | Armários masculino | Armários feminino**, e cada opção mostra a sua ocupação em %.

**Desenhos:**
- **Masculino:** usa o desenho `Mapa_Vestiario_001_a_200.svg`, com 200 armários (`armario-001` a `armario-200`) em 17 conjuntos.
- **Feminino:** usa o **mesmo arquivo** do masculino, sem duplicar.
  - Ao abrir a aba Feminino, a tela troca o título para "VESTIÁRIO FEMININO" e aplica um **rosa fraco** no fundo e na estrutura dos armários.
  - As cores das portas (verde, vermelho e amarelo) são as mesmas nos dois vestiários.
- Arquivo único preparado: `static/vestiario.svg`.
  - Ele não tem o bloco `<style>` interno, a legenda desenhada nem as notas "sem vínculo com banco de dados", porque a página tem legenda própria e o mapa agora é ligado ao banco.
  - O desenho e a numeração foram preservados.
- Se um dia o feminino tiver outro layout, basta criar um arquivo próprio e apontar para ele em `static/mapas.js` (`MAPS.feminino.svg`). Os ids das portas precisam seguir o padrão `armario-001`…

**Cadastro:**
- Novo campo **Vestiário** (Masculino ou Feminino). O número do armário fica entre 1 e 200, e vestiário e número são exigidos juntos. O número é gravado sem zeros à esquerda: "012" vira "12".
- As sugestões de número livre mudam conforme o vestiário escolhido.

**Regras do servidor** (iguais às do escaninho, separadas por vestiário):
- Um cadastro ativo por armário.
- Bloqueio por vestiário: bloquear o feminino 5 não afeta o masculino 5.
- O mesmo cadastro pode ter armário **e** escaninho. Liberar encerra o cadastro e libera os dois, e a janela do armário avisa isso.

**Outras mudanças:**
- O endereço de bloqueio virou `POST /api/mapas/bloqueio`, com `{"mapa": "escaninhos" | "masculino" | "feminino", "numero", "bloqueado"}`.
- Os bloqueios ficam em `settings`: `escaninhos_bloqueados`, `armarios_masculino_bloqueados` e `armarios_feminino_bloqueados`.
- Os três mapas abrem em 52%.
- `static/escaninhos.js` foi substituído por `static/mapas.js`, que atende os três mapas.
- Novos testes: `test_vestiario_locker_maps` e `test_password_reset_by_admin`.

---

## 29/10/2026 (tarde): visual e mapa dos escaninhos

### Tela de login

- O fundo agora é azul-escuro (`#171a2e`) na tela inteira, sem a divisão em duas metades.
- O login fica num cartão centralizado, com um branco mais suave (`#f4f5f9`), sombra leve e campos com borda clara.
- O fundo azul que o navegador coloca nos campos de usuário e senha salvos passa a ficar branco suave.
- Saíram a logo DPSP e os textos "Cada acesso. Cada movimento. Tudo sob controle." e o rodapé "GATEFLOW · OPERAÇÃO…".
- Ficou só "Prevenção de Perdas / PORTARIA LOGÍSTICA", no canto inferior esquerdo. No celular, o nome fica centralizado acima do cartão.
- Corrigido um problema antigo: a regra de formato do campo Usuário era inválida no Chrome atual e ficava sendo ignorada.

### Barra lateral

- Usa o mesmo azul da tela de login (`#171a2e`, variável `--sidebar` em `static/style.css`).
- A cor da barra do navegador no celular (`theme-color`) acompanha esse azul.

### Veículos

- O ícone do módulo virou um **carro**, no menu e no card "Veículos em movimentação" da Visão geral.

### Módulo Armários e Escaninhos

- O nome agora é **Armários e Escaninhos**, com E maiúsculo.
- **Armário deixou de ser obrigatório.** A regra agora é informar armário **ou** escaninho.
- O campo Escaninho aceita só números de 1 a 216 e sugere os números livres. O número é gravado sem zeros à esquerda: "007" vira "7".

### Mapa dos escaninhos (nova funcionalidade)

O mapa fica na aba Armários e Escaninhos, acima da tabela.

**Desenho:**
- Usa o SVG `Mapa_Armarios_001_a_216.svg`, com 216 portas (`armario-001` a `armario-216`) em 3 blocos de 72.
- A tela usa uma cópia preparada em `static/escaninhos.svg`. Ela não tem o bloco `<style>` interno, porque a política de segurança da página bloqueia estilo embutido, e tem o título "ESCANINHOS | 1 A 216".
- O desenho e a numeração foram preservados. O arquivo original continua na pasta.

**Cores e informações das portas:**
- Cada porta recebe `data-status`: **livre** (verde), **ocupado** (vermelho) ou **bloqueado** (amarelo).
- A porta ocupada mostra o nome curto da pessoa (ex.: "Rafael H."), embaixo da fechadura, sem borda. Nome longo é abreviado e comprimido para não encostar no pino.
- O topo do mapa mostra a **ocupação em %** (ocupados ÷ 216) com uma barra, e as contagens de livres, ocupados e bloqueados.

**Clique na porta:**
- Ocupada: mostra o cadastro vinculado, com os botões **Registro completo** e **Liberar escaninho**. Liberar registra a devolução da chave: o vínculo sai, a porta fica verde e o cadastro fica no histórico.
- Livre: **Vincular colaborador** abre o cadastro com o número preenchido. O administrador também tem **Bloquear**.
- Bloqueada: o administrador tem **Desbloquear**. Porta bloqueada não aceita vínculo.

**Zoom e navegação:**
- Abre em **52%**, com o mapa inteiro e sem barras de rolagem.
- Em telas onde 52% não cabe, abre ajustado à largura; no celular, mantém 52% e rola dentro do mapa.
- Botões − e +, "ver o mapa inteiro" e o campo **Localizar**, que leva até o número digitado.

**Atualização:**
- Ao recarregar a página, tudo volta do banco.
- Ao entrar na aba e a cada 60 s, o mapa busca o que outros computadores gravaram.

**Regras garantidas pelo servidor** (`app.py`), valendo também entre computadores diferentes:
- Escaninho de 1 a 216.
- Só um cadastro ativo por escaninho. A checagem roda em transação exclusiva, então duas máquinas não conseguem pegar o mesmo número ao mesmo tempo.
- Porta bloqueada não aceita vínculo, e porta ocupada não pode ser bloqueada.
- A importação JSON também respeita essas regras.
- Conflito responde com o código 409.
- Bloqueio e desbloqueio são exclusivos do administrador e ficam na auditoria.
- Os bloqueios ficam na tabela `settings`, na chave `escaninhos_bloqueados`.

**Arquivos:**
- Novos: `static/escaninhos.js` e `static/escaninhos.svg`.
- Alterados: `static/app.js`, `static/style.css`, `static/index.html`, `app.py`, `schema.json` e `test_app.py` (novo teste `test_escaninho_map_rules`).

### Tabelas

- Nas tabelas dos módulos, os cabeçalhos e textos longos quebram em duas linhas, e o espaço entre colunas diminuiu.
- Não há mais rolagem lateral a partir de 1366 px. No celular, a rolagem continua.

### Usuários e permissões

- Ganhou o botão de **atualizar** ao lado de "online · usuários", que recarrega a lista sem recarregar a página.

---

## 29/10/2026 (manhã): banco na pasta de rede e executável

Motivo: a máquina da portaria desliga com as quedas de energia e não pode servir de servidor. Cada computador roda o próprio `.exe`, e todos usam o mesmo banco numa pasta de rede.

- **Banco em modo clássico do SQLite** (`journal_mode=DELETE`) no lugar do WAL, porque o WAL não funciona em pasta de rede. Se uma gravação for interrompida, ela é desfeita na próxima abertura.
- **Pasta do banco configurável:** na primeira abertura, o `.exe` pergunta a pasta de rede e grava `config.json` ao lado dele. Exemplo: `{"pasta_banco": "\\\\servidor\\portaria", "porta": 8780}`.
- **Verificação do banco ao abrir** (`PRAGMA quick_check`). Se ele estiver danificado, o sistema não abre e indica a pasta de backups.
- **Backup automático** em `backups\` dentro da pasta do banco, ao abrir e a cada 6 horas, guardando as últimas 60 cópias.
- **Aviso claro** se a pasta de rede estiver fora do ar.
- **Executável `PrevencaoPerdas.exe`:** um arquivo só, com o ícone `icone.ico`, gerado por `gerar_exe.bat`.
  - Abre o navegador sozinho. Se já estiver aberto no computador, só reabre o navegador.
- **Porta padrão 8780**, que pode ser trocada pelo campo `"porta"` do `config.json`.
  - Se a porta estiver ocupada por outro programa, o sistema avisa e sugere outra.
  - Para isso, o sistema reconhece o próprio servidor pelo cabeçalho `Server`.
- **Opções de linha de comando:** `--db` (arquivo do banco), `--port`, `--sem-navegador` e `--redefinir-senha LOGIN`. O `redefinir_senha.bat` usa o `.exe` quando ele existe.
- **Testes:**
  - Novos testes automáticos: modo do banco e backup, configuração da pasta e reconhecimento do próprio servidor.
  - Teste manual com dois `.exe` gravando ao mesmo tempo num caminho de rede (`\\localhost\C$\...`): 80 gravações simultâneas, sem perda e com o banco íntegro.
- O README ganhou a seção "Executável com banco na pasta de rede".

## Antes de 29/10/2026

Funcionalidades que já existiam (detalhes no README):
- Login individual com perfis administrador e operador.
- Abas liberadas por operador.
- Usuários online.
- Registro de retorno.
- Auditoria.
- Importação e exportação JSON.
- Backup SQLite.
- Os módulos de Veículos, Rotas, Saída de materiais, Devoluções, Equipamentos móveis, Armários e Escaninhos e Cadastro de pessoas.
