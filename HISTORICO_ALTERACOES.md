# Histórico de alterações

Este documento explica o que é o sistema Prevenção de Perdas (GateFlow), por que ele foi criado e como funciona. Depois vêm as mudanças, da mais recente para a mais antiga.

## Sobre o projeto

### Por que foi criado

A Prevenção de Perdas do CD Bahia controlava a portaria numa planilha do Excel (`Pasta_de_Trabalho_Portaria.xlsb`), com uma aba para cada controle. A planilha tinha limites:
- não identificava quem fez cada lançamento;
- não impedia dois lançamentos para o mesmo armário ou a mesma chave;
- não mostrava, na hora, o que estava em aberto;
- ficava travada quando alguém a deixava aberta.

O sistema substitui esses controles com:
- login individual;
- regras garantidas pelo servidor;
- auditoria de tudo;
- um banco único, usado por todos os computadores da portaria.

A planilha original serviu só de mapa dos controles (ver `MAPEAMENTO_PLANILHA.md`). Nenhum dado pessoal dela foi copiado.

### O que o sistema controla

O menu tem três grupos. Dentro de cada grupo, os módulos aparecem em ordem alfabética.

| Grupo | Módulo | O que registra |
|---|---|---|
| Portaria | Cadastro de pessoas | Entrada de visitantes e terceirizados: nome, documento (CPF, RG ou CNH), empresa e data e hora da entrada. |
| Operação logística | Chaves de setores | Retirada e devolução das chaves dos 8 setores controlados (Medicamentos Especiais, Alimentos, Psicotrópicos, Termolábeis, Reversa 01 a 03 e Visados 2). Só uma retirada por chave de cada vez. |
| Operação logística | Devoluções | Mercadoria devolvida: transportador, fornecedor, motivo, volumes, conferente e quem conferiu pela Prevenção. |
| Operação logística | Rotas | Saída e retorno das rotas: rota, tipo, placa, condutor, auxiliar, lacres e quem liberou. |
| Operação logística | Saída de materiais | Materiais que saem do CD, com a autorização. |
| Patrimônio e controle | Armários e Escaninhos | Vínculo do colaborador ao escaninho (216) e aos armários dos vestiários masculino (1 a 300) e feminino (157 a 300), com mapa clicável, bloqueio de portas e cópia de chave. |
| Patrimônio e controle | Equipamentos móveis | Retirada e retorno de empilhadeiras, patoladas e JETs (lista fixa). |

A **Visão geral** mostra os números do dia e o que está em aberto. Veículos existiu até 17/11/2026. Os registros antigos de Veículos continuam no banco, mas não aparecem nas telas.

### Como funciona

**Instalação e banco**
- O sistema é um programa só, o `PrevencaoPerdas.exe`. Ele abre o navegador no próprio computador (`127.0.0.1:8780`). Não precisa de internet nem de instalar nada.
- **Todos os computadores usam o mesmo banco SQLite**, que fica numa pasta de rede. Não há servidor central, porque a máquina da portaria desliga nas quedas de energia.
- O banco usa o modo clássico do SQLite, sem WAL. Cada gravação reserva o banco por um instante (`BEGIN IMMEDIATE`). Assim, dois computadores não pegam o mesmo armário nem a mesma chave ao mesmo tempo.
- **Backup automático** em `backups\`, na pasta do banco: ao abrir e a cada 6 horas, guardando as 60 últimas cópias. Ao abrir, o sistema também confere se o banco está íntegro.

**Usuários**
- Login individual. O **administrador** cria usuários, edita, exclui, importa, bloqueia portas e chaves e inclui ou exclui itens das listas.
- O **operador** lança, consulta e registra retornos, e vê só as abas que o administrador liberar.
- O operador sai sozinho depois de 2 minutos parado. O administrador não sai.

**Registros**
- Todo registro guarda quem lançou e quando. O texto é gravado em MAIÚSCULAS.
- Registros com retorno (Rotas, Equipamentos, Armários e Escaninhos, Chaves de setores) ficam **Em aberto** até alguém usar **Registrar retorno**.
- Cada ação importante fica na **auditoria**: login, criação, edição, exclusão, bloqueios, importação e itens das listas.

**Bases de consulta**
- São três: colaboradores, terceirizados e listas de escolha (rotas, placas, fornecedores etc.). Elas ficam dentro do banco SQLite.
- **O próprio sistema alimenta as bases:**
  - um terceirizado cadastrado já é encontrado pelo documento;
  - uma matrícula nova entra na base de colaboradores;
  - os valores usados entram nas listas.
- A planilha `Dados do projeto.xlsx` (Configurações › Importar planilha) serve só para carregar o que já existia. Reimportar atualiza e acrescenta, mas não apaga nada.
- Nos formulários, o administrador tem **+ Novo**, para incluir um item na lista na hora, e **Editar**, para excluir um item com o ✕.
- Na importação, uma mesma matrícula ou um mesmo CPF com nomes diferentes fica só com a última linha. Por isso, a importação lista esses casos para correção.

**Arquivos principais**

| Arquivo | Função |
|---|---|
| `app.py` | Servidor, regras, login e banco. |
| `bases.py` | Planilha, bases e buscas. |
| `schema.json` | Módulos, campos e ordem do menu. |
| `static/` | Telas: `app.js`, `bases.js`, `mapas.js`, `chaves_setores.js` e `style.css`. |
| `test_app.py` | Testes automáticos. |
| `iniciar.py` e `gerar_exe.bat` | Montam o `.exe`. |

### Linha do tempo resumida

| Data | O que mudou |
|---|---|
| Antes de 29/10 | Primeira versão: login, perfis, 7 módulos, auditoria, JSON e backup. |
| 29/10 | Banco na pasta de rede, `.exe`, visual novo e mapa dos escaninhos. |
| 30/10 | Armários dos vestiários, bases por planilha, MAIÚSCULAS, `.exe` sem janela preta, motivo do bloqueio, saída por inatividade e cópia de chave. |
| 03/11 | Planilha única com todas as bases e listas suspensas. |
| 04/11 | Maiúsculas em todos os campos. |
| 05/11 | 300 armários, feminino de 157 a 300, bloqueio em sequência e marca de terceirizado. |
| 06/11 | Devoluções com 0 volume e "Conferido por (Prevenção)"; tabelas em uma linha. |
| 09/11 | "Liberado por" em Rotas. |
| 10/11 | Nomes da base em Rotas, colaborador de retorno, data de entrada, lista fixa de equipamentos e tabela de Rotas compacta. |
| 13/11 | Bases alimentadas pelo próprio sistema, "+ Novo", ocupação sem as portas bloqueadas e JET 04/05. |
| 17/11 | Chaves de setores no lugar de Veículos, menu em ordem, nomes sem matrícula em Rotas e aviso de repetidos na importação. |
| 18/11 | "Editar" para excluir itens das listas; o "+ Novo" inclui o item na ordem certa. |

## Situação atual (18/11/2026)

- O projeto está em `Documents\projetospython\projeto-portariaprevencao\GateFlow`. O código fica no GitHub, na branch `feat/armarios-300-retorno-sobre`.
- O sistema está em implantação no CD, com o banco na pasta de rede.
- Os testes automáticos passam: `python -m unittest` (44 testes).
- **`dist\PrevencaoPerdas.exe` foi gerado em 18/11/2026, às 09:54**, com todas as mudanças listadas abaixo. Ele roda sem janela (sem a tela preta). Foi testado numa pasta temporária, com banco descartável.
- **A pasta de rede ainda não recebeu esse `.exe`.** Até a troca, os computadores continuam com a versão anterior.

### Como está instalado no CD

- **Pasta de rede:** `\`\servidor\pasta-do-banco``. O usuário pode deixá-la oculta: o sistema funciona igual.
- **Dentro dela:**
  - `PrevencaoPerdas.exe`: um só, para todos os computadores.
  - `config.json`: aponta para a própria pasta. Uma cópia pronta fica em `dist\config.json`.
  - `redefinir_senha.bat`
  - `portaria.db`: o banco, criado sozinho na primeira abertura.
  - `backups\`: criada sozinha. Uma cópia a cada 6 h, guardando as 60 últimas.
- **Cada computador** tem só um atalho na Área de Trabalho apontando para o `.exe` da rede. Para criar um atalho com a pasta oculta, digite o caminho na barra de endereço do Explorador.
- O endereço `127.0.0.1:8780` significa "este próprio computador". Cada computador roda a sua cópia do sistema, e todos usam o mesmo banco. Ver os mesmos dados em todos os computadores é o comportamento esperado.
- Os arquivos da rede foram apagados por engano uma vez e recopiados. O banco da rede recomeçou do zero.
- Guia ilustrado da implantação: https://claude.ai/artifact/69BdRCgdfQJmrvCkZQGj7K. **Está desatualizado em dois pontos:** ainda manda copiar o `.exe` para cada computador e manter a janela preta aberta.

### Como atualizar o sistema

1. Gere o `.exe` com `gerar_exe.bat`, ou peça para gerar. O resultado fica em `dist\PrevencaoPerdas.exe`.
2. Em **todos** os computadores, feche o sistema: Gerenciador de Tarefas (Ctrl+Shift+Esc) › **PrevencaoPerdas** › **Finalizar tarefa**. Reiniciar o computador também serve.
3. Copie o `.exe` novo por cima do antigo na pasta de rede. Se o Windows disser que o arquivo está em uso, algum computador ainda está com o sistema aberto.
4. O banco, o `config.json` e os atalhos não mudam. Tabelas novas são criadas sozinhas ao abrir.

### Desenvolvimento no mesmo computador

- Rodando pelo código (`py -3 app.py`), o sistema usa o banco de testes `GateFlow\dados\portaria.db` e nunca o da rede, porque não existe `config.json` na pasta `GateFlow`. **Não copie o `config.json` para essa pasta.**
- Rode o código em outra porta para não confundir com o sistema real: `py -3 app.py --port 8781`.
  - `127.0.0.1:8780` é o sistema real, aberto pelo atalho.
  - `127.0.0.1:8781` é o de testes.
- Para conferir a tela, use um banco descartável e o Chrome sem janela controlado por script (CDP). O PyPI está bloqueado na rede, então não dá para instalar o Playwright.

### Próximos passos combinados

1. Trocar o `.exe` da pasta de rede pelo de 18/11/2026, 09:54 (ver "Como atualizar o sistema").
2. Corrigir a planilha `Dados do projeto.xlsx` e importar de novo:
   - Na aba Colaboradores, dar a cada pessoa a sua matrícula (três pessoas novas estavam com a mesma matrícula) ou deixar o campo em branco.
   - Na aba Acesso de Terceiros, corrigir os CPFs repetidos, como o 000.000.000-00.
3. Testar com dois computadores: cadastrar num, apertar F5 no outro, fechar um e ver o outro continuar.
4. Opcional: pedir à TI que só os usuários do sistema acessem a pasta de rede. O banco tem nomes e CPFs, e ocultar a pasta não protege.

### Ideias oferecidas e ainda não feitas

- Exportação em **Excel (.xlsx)** por módulo e período, para relatórios. "Exportar JSON" serve para integração com outros sistemas, não para relatório, e não é backup.
- Atualizar o guia ilustrado para a instalação com o `.exe` na rede.

### Decisões registradas

- **Reset do banco: não fazer por enquanto.** O banco tinha 48 KB, e o SQLite aguenta milhões de registros. Se um dia crescer, a ideia é arquivar só os registros concluídos antigos (com backup antes), sem apagar a auditoria nem os vínculos ativos.
- **Cada computador roda o próprio `.exe`** e todos usam o mesmo banco na rede, em modo clássico do SQLite (sem WAL). Não haverá servidor central: a máquina da portaria desliga com as quedas de energia.
- **Cópia da chave:** o armário não pode ser liberado enquanto a cópia não voltar, e só uma cópia fica em uso por vez. Combinado assim; pode mudar se o usuário pedir.
- **Saída por inatividade:** 2 minutos, só para operadores. O administrador não sai sozinho, a pedido do usuário. Cuidado: ao se afastar de um computador que não é o seu, clique em **Sair**.
- **Valor fora da lista:** não pode ser escolhido na tela. Desde 13/11/2026, o administrador o inclui na hora com **+ Novo**, sem planilha. Desde 18/11/2026, ele exclui um item errado com **Editar**. A opção "Outra (digitar)" chegou a existir e saiu a pedido do usuário.
- **O sistema se alimenta do banco, não da planilha** (13/11/2026). A planilha é só a carga inicial.
- **Chaves de setores:** uma chave por setor, só controle, como os escaninhos. O usuário pediu para não perguntar a quantidade de cópias.
- **Excluir item da lista:** o botão Editar abre um painel com ✕, porque a lista do navegador não aceita um ✕ em cada item. O usuário escolheu isso em vez de uma lista feita no sistema.

---

## 18/11/2026: excluir item das listas ("Editar")

- Ao lado do "+ Novo" das listas (Rota, Placa, Fornecedor etc.) há um botão **Editar**, só para o administrador. Ele abre os itens da lista, cada um com um **✕**. O ✕ pede confirmação e exclui o item do banco.
- Os registros que já usam o valor continuam como estão. A exclusão fica no log de auditoria.
- Novo endereço: `DELETE /api/bases/listas` (só o administrador).
- O item incluído pelo "+ Novo" entra na ordem da lista, e não mais no fim.
- O `.exe` foi gerado em 18/11/2026, às 09:54, com esta mudança. A versão das 08:39, do mesmo dia, tinha só a parte de 17/11 (noite).

## 17/11/2026 (noite): nomes sem matrícula em Rotas e aviso de matrícula/documento repetido

- **Rotas: as sugestões de condutor e auxiliar buscam em todos os nomes.** Entram os colaboradores com matrícula, os nomes sem matrícula e quem já foi condutor ou auxiliar em alguma rota. A busca nova fica em `/api/bases/nomes`.
- **Aba Colaboradores:** uma linha com nome e sem matrícula não é mais ignorada. Ela entra só como nome, para essas sugestões, e não aparece na busca por matrícula. A importação mostra "N só com nome (sem matrícula)".
- **Aviso de repetidos:** se uma mesma matrícula ou um mesmo CPF/RG aparece com nomes diferentes na planilha, cada linha substitui a anterior e só a última fica. Agora a importação lista esses casos, até 30, e diz "e mais N" quando há mais. Do CPF, o aviso mostra só o final.
  - Na planilha do usuário, uma mesma matrícula tinha sido usada para três pessoas novas, e só a última ficava no banco.
  - A aba de terceiros tinha cerca de 80 CPFs repetidos com nomes diferentes. Um deles era o 000.000.000-00, usado para 34 pessoas.

## 17/11/2026 (09:08): mais setores nas Chaves de setores

- Entraram os setores Reversa 01, Reversa 02, Reversa 03 e Visados 2. Agora são 8 setores, cada um com uma chave.

## 17/11/2026 (08:58): menu em ordem alfabética

- Dentro de cada grupo do menu, os módulos aparecem em ordem alfabética. Os grupos continuam na mesma sequência: Portaria; Operação logística (Chaves de setores, Devoluções, Rotas, Saída de materiais); Patrimônio e controle (Armários e Escaninhos, Equipamentos móveis). A mesma ordem vale para a tela Novo registro.

## 17/11/2026 (08:47): Chaves de setores no lugar de Veículos

- **Veículos saiu do sistema.** Os registros antigos continuam no banco, mas não aparecem mais nas telas. A cópia JSON exportada continua trazendo esses registros. O cartão do painel virou "Rotas em andamento".
- **Novo módulo "Chaves de setores"**, no lugar de Veículos no menu. Ele cobre os setores Medicamentos Especiais, Alimentos, Psicotrópicos e Termolábeis, com **uma chave por setor**.
  - Funciona como os armários, mas por tabela, sem desenho. Cada setor aparece como Livre, Em uso (com quem e desde quando) ou Bloqueada (com motivo, quem bloqueou e quando).
  - **Entregar chave:** pela matrícula, com o nome preenchido pela base de colaboradores. A hora da retirada já vem preenchida. Um colaborador novo entra na base.
  - **Registrar devolução:** qualquer usuário pode registrar. O registro é concluído e a chave volta a ficar livre.
  - O servidor não deixa entregar uma chave que já está em uso ou bloqueada, nem quando dois computadores tentam ao mesmo tempo.
  - **Bloquear e desbloquear:** só o administrador, sempre com motivo. Uma chave em uso não pode ser bloqueada. Tudo fica registrado na auditoria.
  - O histórico completo das entregas aparece na tabela "Registros do módulo", logo abaixo.
  - Um operador com abas restritas só vê o módulo se o administrador marcar essa aba nas permissões dele.

## 13/11/2026 (15:02): bases alimentadas pelo próprio sistema, ocupação sem bloqueadas e JET 04/05

- **As bases agora crescem com os lançamentos, no banco SQLite.** A planilha "Dados do projeto.xlsx" serve só para carregar os dados que já existiam. Antes, só a planilha alimentava as buscas, e um terceirizado recém-cadastrado não era encontrado.
  - Cadastro de pessoas: nome, documento e empresa entram na base de terceirizados. Com 11 dígitos, o documento conta como CPF. Fora disso, conta como RG ou CNH. Um "RG", "CPF" ou "CNH" digitado antes do número é ignorado.
  - Armários e Escaninhos, Saída de materiais e Equipamentos móveis: um colaborador novo entra na base pela matrícula e pelo nome. Quem já está na base mantém o nome, o cargo e a situação da planilha.
  - Devoluções, Rotas e Veículos: os valores usados entram nas listas de escolha.
  - Na primeira abertura deste `.exe`, os registros já gravados alimentam as bases uma única vez. Assim, o terceirizado cadastrado hoje passa a ser encontrado.
  - Nos formulários, cada lista de escolha (transportador, fornecedor, motivo, rota, placas, condutor, auxiliar) tem o botão **+ Novo**, só para o administrador. Ele inclui o valor na lista na hora e já o deixa escolhido, sem planilha. A inclusão fica na auditoria. Uma primeira versão punha esse campo em Configurações; o usuário preferiu o botão no formulário.
- **A ocupação dos armários e escaninhos não conta as portas bloqueadas:** ocupadas ÷ (ocupadas + livres).
- **Equipamentos móveis:** entraram JET 04 e JET 05.

## 10/11/2026 (21:31): correção do retorno de equipamentos antigos e tabela de Rotas mais compacta

- **Correção:** registrar o retorno de um equipamento cadastrado antes da lista fixa (por exemplo "EMPILHADEIRA" sem número) dava "Equipamento: opção inválida". Agora, no retorno e na edição, o valor que já estava salvo continua válido, e o formulário de edição o mostra na lista. Um registro novo, ou a troca por outro valor fora da lista, continua sendo recusado. Isso vale para todas as listas fixas.
- **Rotas, tabela compacta:** a tabela tinha 14 colunas e ganhava rolagem lateral. Agora três pares dividem a mesma coluna, com o segundo valor em letra menor embaixo: Condutor / auxiliar, Saída / lacre e Retorno / lacre (chave `stack` do schema). São 11 colunas, que cabem sem rolagem em 1600px e em 1920px de largura. O formulário e a busca não mudaram.
- O `.exe` foi gerado em 10/11/2026, às 21:31. Testes novos: `test_records_saved_before_the_equipment_list_can_still_be_returned` e `test_route_table_stacks_pairs_to_fit` (37 testes no total).

## 10/11/2026 (noite): lista fixa de equipamentos, Prevenção opcional no retorno e matrícula antes do nome

- **Equipamentos móveis, "Equipamento":** virou uma lista fixa com EMPILHADEIRA 01, 02 e 03, PATOLADA 01, 02 e 03 e JET 01, 02 e 03. O servidor recusa qualquer outro valor. Os registros antigos (por exemplo "EMPILHADEIRA" sem número) continuam aparecendo como estão, mas, se alguém editar um deles, vai precisar escolher um item da lista.
- **Equipamentos móveis, "Conferido por (Prevenção)":** deixou de ser obrigatório em "Registrar retorno" (chave `returnOptional` do schema). Em Veículos ele continua obrigatório.
- **Matrícula antes do nome:** em Saída de materiais, Equipamentos móveis e Armários e Escaninhos, a Matrícula vem antes do Colaborador, na tabela e no formulário. O nome continua em negrito na tabela.
- O `.exe` foi gerado em 10/11/2026, às 21:22. Testes novos: `test_equipment_is_picked_from_a_fixed_list` e `test_matricula_comes_before_the_name`. Os testes antigos de Equipamentos passaram a usar itens da lista (35 testes no total).

## 10/11/2026: nomes da base em Rotas, colaborador de retorno e data de entrada

- **Rotas: Condutor e Auxiliar** deixaram de ser listas fixas (vindas da aba "Placa do carro e caminhão") e agora sugerem nomes da **base de colaboradores** a partir da 2ª letra digitada. A lista mostra matrícula e cargo. Um nome fora da base ainda pode ser digitado. Rota e Placa continuam como listas.
- **Equipamentos móveis:** novo campo **"Colaborador de retorno"**, porque quem devolve nem sempre é quem retirou. É obrigatório em "Registrar retorno", sugere nomes da base de colaboradores e aparece como coluna na tabela. O campo "Colaborador" (de quem retirou) não muda.
- **Cadastro de pessoas:** novo campo obrigatório **"Entrada"** (data e hora). Ele já vem com o horário atual e pode ser alterado para registrar um acesso de outro dia. A coluna "Data e hora" continua mostrando quando o registro foi feito no sistema.
- Registros antigos ficam com "—" nas colunas novas. Se alguém editar um deles, vai precisar preencher o campo.
- Conferido no navegador, com banco de teste: as sugestões aparecem no formulário de Rotas e no retorno de Equipamentos, e o campo Entrada vem preenchido. Em 1600px de largura nenhuma tabela passa da tela; em 1366px, Veículos, Rotas, Devoluções, Equipamentos e Armários ganham rolagem lateral.
- O `.exe` foi gerado em 10/11/2026, às 21:01. Testes novos: `test_person_access_keeps_the_day_they_came_in`, `test_equipment_return_names_who_brought_it_back` e `test_route_names_are_suggested_from_the_employee_base` (33 testes no total).

## 09/11/2026: "Liberado por" em Rotas

- Novo campo obrigatório **"Liberado por"** em Rotas, logo depois de "Saída". Ele registra quem liberou a rota, digitado à mão e salvo em maiúsculas. Aparece também como coluna na tabela.
- Rotas antigas ficam com "—" nessa coluna. Se alguém editar uma delas, vai precisar preencher o campo.
- O `.exe` foi gerado em 09/11/2026, às 12:20. Teste novo: `test_route_records_who_released_it`. Os testes que criavam rotas passaram a informar o campo (30 testes no total).

## 06/11/2026 (tarde): "Conferido por (Prevenção)" no retorno de Equipamentos móveis e Veículos

- Ao clicar em **Registrar retorno** em Equipamentos móveis ou Veículos, agora também é obrigatório informar **"Conferido por (Prevenção)"**. O valor é salvo em maiúsculas. Na tabela, a coluna se chama **Prevenção**, como em Devoluções.
- Ao abrir o registro (retirada ou saída), o campo aparece como opcional, igual aos outros campos de retorno.
- Os registros já devolvidos ficam com "—" nessa coluna. "Recebido por" (Equipamentos) continua sendo quem estava logado.
- O `.exe` foi gerado em 06/11/2026, às 15:22. Teste novo: `test_return_asks_who_checked_for_prevention`. Dois testes antigos foram ajustados porque o retorno agora pede esse campo (29 testes no total).

## 06/11/2026: Devoluções aceitam 0 volume e registram quem conferiu pela Prevenção

- **Volumes = 0:** antes o servidor recusava o 0 como "número inválido". Agora o 0 é aceito. Negativos e números quebrados continuam recusados. Na Saída de materiais, a quantidade continua precisando ser pelo menos 1.
- **Novo campo "Conferido por (Prevenção)":** é obrigatório e fica logo após "Conferente". O valor é salvo em maiúsculas. O operador logado continua sendo registrado automaticamente, como antes.
- **Tabelas em uma linha e em maiúsculas (todos os módulos e a Visão geral):** títulos e células não quebram mais linha, e o conteúdo das células aparece em maiúsculas (só na exibição; os dados salvos não mudam, por exemplo "Integral" e nomes antigos de usuários). O espaço entre colunas caiu de 9px para 7px. Em Devoluções, o cabeçalho da tabela usa títulos curtos (Motivo, Tipo, Prevenção, pela chave "columns" do schema); o formulário mantém os nomes completos. Em 1600px de largura ou mais todas as tabelas cabem na tela; em 1366px, Devoluções e Armários e Escaninhos ganham rolagem lateral dentro da tabela.
- Devoluções antigas não têm esse campo. Se alguém editar uma delas, vai precisar preenchê-lo.
- O `.exe` foi gerado em 06/11/2026, às 15:22, com estas mudanças. Foi testado em uma pasta temporária, com banco descartável.
- Teste novo: `test_devolucao_accepts_zero_volumes_and_requires_prevention_checker` (28 testes no total).

## 05/11/2026: feminino de 157 a 300, bloqueio em sequência e marca de terceirizado

### Vestiário feminino

- O feminino agora vai de **157 a 300** (144 armários, conjuntos 14 a 25). O masculino continua de 1 a 300, a pedido. Os números 157 a 300 existem nos dois vestiários.
- O desenho continua um só (`static/vestiario.svg`): no feminino, a tela tira os conjuntos 1 a 13 e sobe os demais.
- Novos vínculos, bloqueios e marcas fora da faixa são recusados.
- **Registro antigo com armário feminino abaixo do 157:** continua valendo e pode ser editado sem trocar de armário e liberado pela tabela de registros, mas não aparece no mapa nem na ocupação.
- Bloqueios antigos abaixo do 157 ficam guardados, sem efeito.

### Bloquear sequência

- Botão **Bloquear sequência** nos três mapas, só para o administrador. Informe do número, até o número e o motivo. O mesmo formulário desbloqueia, sem pedir motivo.
- **Portas ocupadas ficam de fora** e aparecem no aviso. Portas já bloqueadas mantêm o motivo que tinham.
- A auditoria grava uma linha por sequência, com a faixa pedida.

### Marca de terceirizado

- Ao clicar em uma porta, o administrador vê **Marcar como terceirizado** ou **Tirar marca de terceirizado**. Vale para armários e escaninhos.
- A porta ganha borda roxa e a etiqueta **TERC**, e a janela da porta mostra o aviso. O operador vê a marca, mas não pode mudá-la.
- **A marca só sinaliza**, a pedido: não muda a situação da porta, que continua livre, ocupada ou bloqueada, e não limita quem pode ser vinculado.
- A marca fica na porta: continua depois que o cadastro é liberado, até o administrador tirar.

### Testes

- `test_feminino_lockers_start_at_157`, `test_door_sequence_block` e `test_door_terceirizado_mark` são novos. `test_vestiario_locker_maps` e `test_door_block_requires_reason` passaram a usar armários femininos a partir do 157.

O `.exe` foi gerado com estas mudanças em 05/11/2026, às 14:59.

## 05/11/2026: 300 armários por vestiário e fim do campo Patrimônio

### Armários

- Masculino e feminino passaram de 200 para 300 armários. Os escaninhos seguem com 216.
- Agora são 25 conjuntos iguais, de 12 portas (3 colunas e 4 andares), em `static/vestiario.svg`.
- O conjunto 17 tinha 8 portas e passou a ter 12, a pedido. As portas 193 a 200 mudaram de lugar no desenho, mas os números não mudaram, e cadastros e bloqueios continuam valendo.
- **A disposição dos conjuntos 17 a 25 é uma proposta e precisa ser confirmada com o vestiário real.**
- `Mapa_Vestiario_001_a_200.svg` não foi alterado e continua sendo o desenho original de 200 portas.

### Equipamentos móveis

- O campo **Patrimônio / identificação** saiu do formulário e da tabela e deixou de ser obrigatório.
- Os valores já salvos continuam no banco e nos arquivos exportados, sem aparecer na tela. Por isso o módulo tem `"retired":["patrimonio"]` no `schema.json`.
- Sem isso, um equipamento antigo em aberto não conseguiria registrar o retorno, e editar o registro apagaria o valor.

- O campo **Recebido por** saiu do cadastro e do registro de retorno. Quem recebe é o usuário logado que registra o retorno (`returned_by`).
- A coluna "Recebido por" continua na tabela e é preenchida sozinha (`"returnerLabel"` no `schema.json`). Nomes digitados antes da mudança continuam aparecendo.
- Uma devolução informada direto no cadastro ou na edição não passa por "Registrar retorno", então a coluna fica com "—".

### Rodapé e janela Sobre

- O rodapé mostra **Sobre** e **Desenvolvido por Rafael Higino**, inclusive em telas estreitas.
- **Sobre** abre uma janela com o resumo do sistema, o que ele controla e como funciona.

### Testes

- `test_patrimonio_left_the_form_but_old_values_survive`, `test_equipment_receiver_is_the_logged_in_user` e `test_footer_credits_the_author_and_opens_about` são novos, e `test_vestiario_locker_maps` passou a cobrir a porta 300.

## 04/11/2026: maiúsculas em todos os campos digitados

- Todo campo de texto do sistema agora aparece em maiúsculas enquanto se digita. Entraram a busca, o login, o nome do usuário (no primeiro acesso e em Usuários) e o nome da unidade.
- **Ficam como estão:**
  - A senha, que diferencia maiúsculas de minúsculas e aparece só como pontos.
  - Datas, números, arquivos e listas de opção.
  - Os textos de exemplo dentro dos campos vazios, como "Buscar nome, placa, empresa ou documento…".
- O servidor grava o nome do usuário, o login e a unidade em maiúsculas. Isso substitui a regra de 30/10/2026, que deixava o login de fora.
- **Quem já tem login continua entrando:** o login não diferencia maiúsculas de minúsculas, então "maria.jose" e "MARIA.JOSE" são o mesmo usuário.
- **Dados já gravados não foram convertidos:** nomes e logins de usuários já criados e o nome da unidade ("CD Bahia") mudam só quando forem salvos de novo. O login não pode ser editado na tela, então os já criados continuam como estão.
- O nome no topo da tela continua no formato "Maria José", porque a tela o formata.
- Novo teste: `test_user_and_unit_text_saved_uppercase`. Quatro testes antigos foram ajustados para a regra nova.
- O `.exe` foi gerado com esta mudança em 04/11/2026, às 08:48.

## 03/11/2026: planilha única, listas suspensas e alinhamento dos formulários

Em **Configurações > Bases de dados (.xlsx)**, um único botão **Importar planilha .xlsx** substitui os três. O arquivo (`Dados do projeto.xlsx`) traz uma aba por base:

| Aba | A aba é reconhecida se o nome tiver | Colunas | Uso no sistema |
|---|---|---|---|
| Colaboradores | `COLABORADOR` | Situação, Matricula, Nome Completo, Cargo | Igual a antes. |
| Acesso de Terceiros | `TERCEIR` | Nome, CPF, RG, Empresa/Transportadora | Igual a antes. |
| Fornecedores | `FORNECEDOR` | Transportador, Fornecedor, Motivo | Igual a antes. |
| Placa do carro e caminhão | `PLACA` | Placas dos Caminhoes, Placa do Carro, Condutor, Auxiliar, Rota | **Rotas:** Rota, Placa (caminhões), Condutor e Auxiliar. **Veículos:** Placa (carros) e Motorista (lista de condutores). |

**Regras da importação:**
- Maiúsculas e acentos no nome da aba não importam. Abas com outros nomes não são usadas e aparecem citadas no resultado.
- Só as abas presentes no arquivo são atualizadas. As outras bases ficam como estão.
- Erro em uma aba cancela a importação inteira, e a mensagem cita a aba. Duas abas da mesma base também são recusadas.
- Os limites são 10 MB por arquivo e 20.000 linhas por aba. Reimportar continua sem apagar nada.
- **Placas** entram no formato gravado nos cadastros, sem traço nem espaço: `FUP- 4280` vira `FUP4280`. Placa inválida fica fora da lista e é contada como ignorada.

**Como os campos aparecem:**
- Toda lista suspensa tem o mesmo formato de Tipo de rota:
  - **Rotas:** Rota, Placa, Condutor e Auxiliar.
  - **Veículos:** Placa e Motorista.
  - **Devoluções:** Transportador, Fornecedor e Motivo.
  - **Armários e Escaninhos:** Escaninho e Armário, só com as portas livres. O Armário depende do Vestiário escolhido.
- **Valor fora da lista não pode ser escolhido** (decisão do usuário). A portaria anota, o administrador acrescenta na planilha e reimporta, e o registro é lançado depois.
- Sem lista importada, os campos da planilha continuam como texto. Ao editar um registro com valor fora da lista, o valor continua disponível.
- **Nome** (colaborador e terceiro) continua com busca ao digitar, porque a base pode ter milhares de pessoas. O painel de resultados tem o visual da lista aberta e aceita digitar um nome fora da base.
- O preenchimento automático do navegador foi desligado nos formulários de registro e de retorno.
- **Alinhamento:** os campos de cada linha começam na mesma altura e têm 47 px. A causa era a regra `.modalbody .field+.field`, que dava margem a todos os campos menos o primeiro.

**Servidor:**
- `POST /api/bases` recebe o arquivo e devolve `{abas: {base: contagens}, ignoradas: [...]}`. O endereço antigo `POST /api/bases/<base>` saiu.
- A auditoria grava uma linha por aba importada.
- As novas listas ficam em `base_listas`, nos tipos `placa_caminhao`, `placa_carro`, `condutor`, `auxiliar` e `rota`.
- Novo teste: `test_spreadsheet_workbook_with_all_tabs`.

**Arquivos alterados:** `bases.py`, `app.py`, `static/bases.js`, `static/mapas.js`, `static/app.js`, `static/style.css`, `test_app.py` e `README.md`.

**Executável e testes:**
- `dist\PrevencaoPerdas.exe` gerado às 19:38 (9,2 MB).
- Os 20 testes automáticos passam.
- Uma cópia isolada do `.exe`, sem `config.json` e com banco descartável, passou pelo roteiro no Chrome sem janela: importação, listas de todos os módulos, alinhamento das linhas, portas livres, busca por nome e salvar e editar registros.
- **Não testado:**
  - a planilha real no `.exe`;
  - o `.exe` na pasta de rede;
  - a lista nativa aberta, que não aparece no Chrome sem janela. O usuário aprovou a tela no servidor de testes.

## 30/10/2026: cópia da chave (Armários e Escaninhos)

Quando o colaborador esquece ou perde a chave, a portaria entrega uma cópia **no mesmo cadastro**. O cadastro principal continua em aberto.

- **Entregar:** clique na porta ocupada (ou abra o registro completo) › **Entregar cópia da chave**. Informe o motivo (Esqueceu a chave, Perdeu a chave ou Outro) e, se quiser, uma observação de até 300 caracteres, gravada em MAIÚSCULAS.
- **Devolver:** **Registrar devolução da cópia**. A cópia ganha a baixa e o cadastro continua em aberto.
- **Enquanto a cópia não volta:**
  - o cadastro não pode ser liberado, nem pelo retorno nem pela edição do administrador (aviso 409);
  - a janela da porta mostra um aviso em laranja e esconde o botão Liberar;
  - na tabela, o nome ganha a etiqueta **Cópia em uso**.
- Uma cópia em uso por vez. Depois que ela volta, outra pode ser entregue.
- O histórico de cópias aparece na janela da porta e no registro completo.
- Qualquer usuário com acesso à aba pode entregar e receber a cópia. As duas ações ficam na auditoria ("Cópia de chave entregue" e "Cópia de chave devolvida").
- **Servidor:**
  - Nova tabela `copias_chave`, criada sozinha ao abrir.
  - Endereços: `POST /api/records/<id>/copias` (`{motivo, observacao}`) e `POST /api/copias/<id>/devolucao`.
  - `GET /api/records` traz `copias` em cada cadastro de Armários e Escaninhos.
  - Excluir o cadastro apaga as cópias dele.
- Novo teste: `test_key_copy_loans`.
- `dist\PrevencaoPerdas.exe` gerado de novo às 16:21.

## 30/10/2026: saída por inatividade, motivo do bloqueio e nome no topo

### Saída automática por inatividade

- Depois de **2 minutos** sem mexer o mouse, o teclado ou a tela, o sistema sai sozinho e volta para o login.
- O login mostra o aviso "Sua sessão foi encerrada após 2 minutos sem uso".
- O tempo fica na constante `IDLE_MS`, no fim de `static/app.js`.
- **O administrador não sai sozinho.** A saída por inatividade vale só para operadores. O `.exe` foi gerado de novo às 16:25.
- Um formulário aberto e não salvo se perde nessa saída.

### Motivo do bloqueio (escaninhos e armários)

- **Bloquear** agora abre uma janela com o campo **Motivo do bloqueio**. É obrigatório, aceita até 200 caracteres e é gravado em MAIÚSCULAS.
- Ao clicar numa porta bloqueada aparecem o motivo, quem bloqueou e quando. O motivo também aparece ao passar o mouse sobre a porta.
- Portas bloqueadas antes desta versão mostram "Não informado".
- **Servidor:** `POST /api/mapas/bloqueio` exige `motivo` quando `bloqueado` é verdadeiro. Os motivos ficam em `settings`, em `<chave do mapa>_motivos` (por exemplo, `escaninhos_bloqueados_motivos`), no formato `{"número": {"motivo", "por", "em"}}`. Desbloquear apaga o motivo. A auditoria do bloqueio guarda o motivo.
- Novo teste: `test_door_block_requires_reason`.

### Nome no topo

- O canto superior direito mostra o nome (primeiro e último, ex.: "Rafael Higino") e o perfil (**Administrador** ou **Operador**) ao lado das iniciais.
- As iniciais agora usam o primeiro e o último nome (RH), e não mais os dois primeiros.
- No celular, aparecem só as iniciais.

O `dist\PrevencaoPerdas.exe` foi gerado de novo às 15:37 com estas mudanças.

## 30/10/2026: executável sem a janela preta

- O `PrevencaoPerdas.exe` agora é gerado com `--noconsole`. Ao abrir, aparece só o navegador, e o sistema fica rodando em segundo plano.
- **Erros** (pasta de rede fora do ar, porta em uso, banco danificado) aparecem numa **caixa de aviso** do Windows, em vez de sumirem.
- **Uma janela de texto ainda abre quando precisa perguntar algo:**
  - a pasta de rede, quando não existe `config.json`;
  - a nova senha, no `redefinir_senha.bat` (`--redefinir-senha`). Nesse caso, ele usa a própria janela do `.bat`.
- **Encerrar:** no Gerenciador de Tarefas, finalize "PrevencaoPerdas", ou desligue o computador. Faça isso em todos os computadores antes de trocar o `.exe` na pasta de rede.
- Instalação adotada no CD: `.exe`, `config.json` e banco ficam em `\`\servidor\pasta-do-banco``, com um atalho na Área de Trabalho de cada computador.
- Alterados: `iniciar.py` e `gerar_exe.bat`.
- Testado com o `.exe`: o sistema respondeu sem nenhuma janela; a segunda abertura só reabriu o navegador; a pasta inexistente mostrou o aviso; a redefinição de senha abriu a janela para digitar.

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

> Em 03/11/2026, as três importações separadas viraram uma planilha única, e o endereço de importação mudou. Veja a seção daquela data.

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
