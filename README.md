# GateFlow — Portaria logística

Aplicativo funcional em Python com interface web local, banco SQLite e integração JSON. Criado a partir dos controles identificados em `Pasta_de_Trabalho_Portaria.xlsb`. O banco inicial é vazio: nenhum cadastro pessoal ou histórico da planilha foi copiado para o programa.

## Iniciar no Windows

1. Instale Python 3.10 ou superior, com o comando `python` ou o inicializador `py` disponível.
2. Extraia **todos** os arquivos deste ZIP para uma pasta, por exemplo `C:\GateFlow`.
3. Abra `iniciar.bat`. Mantenha a janela do servidor aberta enquanto utilizar o sistema.
4. O navegador abrirá em `http://127.0.0.1:8765`. Se necessário, digite esse endereço manualmente.
5. Na primeira abertura, cadastre seu nome, login e senha de administrador (mínimo de 10 caracteres). Não existe senha padrão.
6. Faça login. Acesse **Usuários e permissões → Criar usuário** para cadastrar os operadores.

O aplicativo não exige `pip install`, internet, Excel ou Node.js. Todo o servidor usa bibliotecas incluídas no Python; a interface usa HTML, CSS e JavaScript locais. Esta entrega contém o código-fonte executável com Python, não um instalador `.exe`.

Linux/macOS: execute `sh iniciar.sh` ou `python3 app.py` dentro da pasta.

## Esqueci a senha

Não existe senha padrão. No computador servidor, abra `redefinir_senha.bat`, informe o login e digite a nova senha duas vezes (ela não aparece na tela). Também funciona com `python app.py --redefinir-senha LOGIN`. A conta é reativada, as sessões dela são encerradas e a ação fica na auditoria. Após 12 senhas erradas, o login fica bloqueado por 5 minutos; reiniciar o servidor libera.

## O que já funciona

- Login, logout e sessões de oito horas.
- Primeiro cadastro de administrador no computador servidor.
- Criação de usuários administradores e operadores; edição do nome, perfil, senha e ativação/desativação.
- 7 módulos com formulários próprios, tabelas, busca, filtros de módulo, situação e data de cadastro, paginação e detalhes.
- Administrador pode editar, concluir e excluir registros.
- Identificação automática do operador, data de cadastro e data da última alteração.
- Auditoria de login, criação, edição, exclusão, usuários, importações, exportações, backup e configuração.
- Importação e exportação JSON; backup consistente do SQLite.
- Visual responsivo com cartões, tabelas arredondadas, transições, modal e suporte à preferência de movimento reduzido.

## Perfis

| Ação | Administrador | Operador |
| --- | --- | --- |
| Cadastrar lançamentos em aberto | Sim | Sim |
| Consultar registros | Todos | Todos |
| Registrar retorno (registros em aberto) | Sim | Sim |
| Editar, corrigir ou excluir | Sim | Não |
| Ver quem está online e o último acesso | Sim | Não |

**Abas por operador:** ao criar ou editar um operador, o administrador marca as abas liberadas (por exemplo, só Cadastro de pessoas). O operador só vê, cadastra e registra retorno nessas abas; a regra é aplicada pelo servidor. Com todas marcadas, abas criadas no futuro também ficam liberadas. Alterar as abas encerra as sessões do operador.
| Criar e administrar usuários | Sim | Não |
| Importar/exportar e baixar backup | Sim | Não |
| Consultar auditoria e configurar unidade | Sim | Não |

As restrições são aplicadas pelo servidor, inclusive em chamadas diretas à API. Dados de cadastro e autoria não dependem do navegador. O administrador não pode desativar ou remover seu próprio perfil administrativo; os usuários são desativados, preservando a autoria histórica dos registros. Alterar um usuário encerra as sessões dele.

**Retorno:** em Veículos, Rotas, Equipamentos móveis e Armários e escaninhos, qualquer usuário pode usar **Registrar retorno** (ícone de seta na linha do registro) enquanto o registro estiver Em aberto. Só os campos de retorno vazios podem ser preenchidos; ao salvar, o registro vira Concluído e o nome de quem registrou o retorno fica gravado. Correções depois disso são feitas pelo administrador em **Editar**.

## Módulos

Veículos; rotas; saída de materiais; devoluções; equipamentos móveis; armários e escaninhos; cadastro de pessoas. Os lançamentos são feitos na página **Novo registro** do menu.

As abas por veículo foram reunidas em Veículos. Consulte `MAPEAMENTO_PLANILHA.md` para o vínculo entre abas e módulos. Macros, fórmulas e histórico da planilha não são executados ou migrados automaticamente. Cadastro de pessoas é independente: nesta versão, não há preenchimento automático dos demais formulários a partir dele. Ele usa um único campo **Documento** (CPF, RG ou CNH, o que a pessoa apresentar) e não tem situação (em aberto/concluído).

## Operação diária

1. Entre com o login individual do operador.
2. No menu, abra **Novo registro**, escolha o tipo de lançamento e preencha os campos obrigatórios.
3. Cadastre e confira o lançamento. O nome do usuário e o horário ficam registrados automaticamente.
4. Use os filtros para localizar os próprios lançamentos. A data do filtro é a de cadastro, não a data operacional digitada no formulário.
5. Solicite ao administrador as correções e conclusões necessárias.
6. Clique em **Atualizar dados** para trazer novos lançamentos de outros computadores. Não há atualização automática em tempo real nesta versão.

O painel considera os registros de todos os operadores. “Acessos em aberto” é uma contagem pela situação registrada, não um sensor de presença. “Ocorrências registradas” inclui o módulo de crachá/fardamento e registros com situação Ocorrência, contando cada registro uma vez.

## Banco e uso em rede

O arquivo `dados/portaria.db` é criado automaticamente na primeira execução. Dados e usuários permanecem após fechar o aplicativo. Deixe o banco no disco local do computador servidor; os outros computadores acessam pelo navegador, sem abrir ou compartilhar o arquivo SQLite diretamente.

Depois de criar o administrador localmente, o comando abaixo permite escutar na rede:

```bash
python app.py --host 0.0.0.0 --port 8765
```

Nos outros computadores, abra `http://IP-DO-SERVIDOR:8765`. O servidor precisa estar ligado. A liberação da porta e o endereço devem ser definidos com a TI. Para uso corporativo com documentos pessoais e senhas trafegando na rede, configure HTTPS por proxy reverso e `GATEFLOW_SECURE_COOKIE=1`. A execução local padrão usa HTTP apenas em `127.0.0.1`; esta entrega não inclui instalação de HTTPS nem publicação na internet.

Para escolher outro banco ou porta:

```bash
python app.py --port 9000 --db "C:\DadosPortaria\portaria.db"
```

Ao usar outra porta, abra o endereço correspondente manualmente. O lançador de navegador `iniciar.py` abre a porta padrão 8765.

Esta versão atende um servidor e um CD, com volume moderado. A lista visível tem páginas, mas os registros autorizados são carregados em memória no navegador; não foi realizado teste de carga. Grandes volumes exigem paginação no servidor e dimensionamento antes de ampliar o uso.

## JSON e integração com outro programa Python

Em **Configurações → Importar JSON**, selecione um arquivo com o formato de `exemplo_importacao.json`. Os campos válidos de cada módulo estão em `schema.json`.

- Arquivo de até 2 MB; na interface, limite conservador de 1,9 MB.
- Até 5.000 registros por arquivo.
- A validação ocorre antes da importação: um registro inválido impede o lote inteiro.
- Importar adiciona registros novos. **Reimportar o mesmo arquivo cria duplicatas.**
- Os IDs, autores e horários de auditoria são gerados novamente no destino. As datas operacionais em `payload` são preservadas. Exportação JSON é para integração e consulta, não para restauração fiel do banco.
- O arquivo de exemplo usa dados fictícios. Não é importado automaticamente.

Um programa Python pode produzir os JSONs para importação, sem acessar o banco:

```python
import json
from pathlib import Path

registro = {
    "module": "pessoas",
    "status": "Em aberto",
    "payload": {"nome": "Pessoa de exemplo", "documento": "CPF de exemplo", "empresa": "Empresa de exemplo", "motivo": "Visita", "area": "RH"}
}
Path("importar.json").write_text(
    json.dumps({"format": "gateflow.records.v1", "records": [registro]}, ensure_ascii=False),
    encoding="utf-8"
)
```

A API também aceita JSON autenticado. Não há token fixo de integração: o cliente precisa de sessão de usuário e token CSRF. Não altere tabelas diretamente enquanto o aplicativo estiver em uso.

## Backup e restauração

O administrador pode baixar um backup em **Configurações → Baixar backup SQLite**. Esse arquivo contém usuários, senhas com hash, sessões, registros, configurações e auditoria. Trate-o como confidencial.

Para restaurar:

1. Pare o servidor com `Ctrl+C` e confirme que ninguém está usando o app.
2. Guarde uma cópia da pasta `dados` inteira antes de qualquer substituição.
3. Coloque o backup no lugar de `dados/portaria.db`. Se existirem `portaria.db-wal` ou `portaria.db-shm`, mova-os para a cópia de segurança anterior para não misturá-los ao banco restaurado.
4. Ainda com o servidor parado, execute na pasta do aplicativo:

```bash
python -c "import sqlite3; c=sqlite3.connect('dados/portaria.db'); c.execute('DELETE FROM sessions'); c.commit(); c.close()"
```

5. Inicie novamente. Os usuários devem fazer login. Se usar `--db`, adapte os caminhos acima.

## Verificação desta entrega

Execute `python -m unittest -v` dentro desta pasta para verificar o servidor. Os testes usam banco temporário, sem modificar os dados da operação. Foram verificados login, permissões de operador, criação e alteração de registros, conflito de edição, importação atômica, exportação, backup e revogação de sessão. O layout de painel e os formulários foram inspecionados no navegador com dados fictícios isolados. O teste visual não substitui homologação com os usuários no ambiente do CD; a navegação autenticada completa não foi executada no navegador de teste. Não foi feita validação em computador Windows real, teste de carga ou integração com catracas, câmeras, leitores ou ERP.

## Arquivos principais

| Arquivo | Finalidade |
| --- | --- |
| `iniciar.bat` / `iniciar.py` | Iniciar no Windows e abrir o navegador |
| `app.py` | Servidor, autenticação, permissões e SQLite |
| `schema.json` | Estrutura dos módulos e campos |
| `static/` | Interface visual |
| `exemplo_importacao.json` | Exemplo fictício de integração |
| `test_app.py` | Testes de integração e validação |

Para encerrar, pressione `Ctrl+C` na janela do servidor. Fechar apenas a aba do navegador não encerra o programa.
