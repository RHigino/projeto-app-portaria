# Relação com a planilha original

A estrutura foi levantada diretamente do arquivo XLSB anexado. As 23 abas foram agrupadas em 11 módulos operacionais e telas de administração. Esta é uma nova implementação dos controles, não uma conversão das macros do Excel. Os campos foram reorganizados e há campos adicionais para rastreabilidade.

| Aba(s) da planilha | Destino no GateFlow | Adaptação |
| --- | --- | --- |
| Menu | Visão geral | Indicadores, busca e acesso aos módulos |
| Configuração | Configurações + estrutura dos formulários | Unidade editável; listas do formulário em `schema.json`. As listas nominais antigas não foram importadas |
| Ctrl_Chaves | Chaves e armários | Colaborador, matrícula/chapa, setor, cargo, armário, escaninho e datas de retirada/devolução |
| Crachá_Fardamento | Crachá e fardamento | Colaborador, matrícula, cargo, supervisor, área, ocorrência e data/hora |
| Saída de Materiais | Saída de materiais | Colaborador, matrícula, cargo, material, quantidade, unidade, autorização, liberação e saída |
| Cadastro de Clientes | Visitantes e terceiros | Nome, documento, empresa, motivo, área; adicionados categoria, responsável, entrada e saída |
| Novo Cadastro | Cadastro de pessoas | Nome, CPF, RG, empresa e telefone |
| DRH, Embrasg, Souza Lima, ElevaLog | Visitantes e terceiros | Categoria diferencia as empresas. CPF/RG ficam em Documento; não mantém abas separadas por empresa |
| Controle de Veículos | Veículos | Módulo unificado da frota |
| FORD KA QWR-4946, FORD KA QWR-4825, (DUCATO) FTK-3823, VAN VERÃO - RFE 5G06 | Veículos | Placa, modelo, motorista, itinerário, KM inicial/final, saída e retorno. Operador de cadastro identificado automaticamente |
| Rotas_03_05, RotasExtras | Rotas e lacres | Rota, tipo regular/extra, placa, condutor, auxiliar, lacres e horários |
| Devolução de Mercadorias, DovoluçõesInativas_2022. | Devoluções | Transportador, fornecedor, NF, motivo, volumes, integral/parcial/sobra, conferente e recebimento. Sem migrar o arquivo histórico inativo |
| Entrada e Saída Colaboradores | Colaboradores | Novos eventos de Entrada/Saída com setor, liderança, motivo e horário |
| Equipamentos Móveis | Equipamentos móveis | Colaborador, matrícula, equipamento, patrimônio, retirada, devolução e recebedor |
| Saída de Grupos | Saída de grupos | Formulário proposto com responsável, setor, quantidade, integrantes, motivo, saída e retorno; requer validação operacional, pois os cabeçalhos não ficaram identificáveis na leitura dessa aba |

Em todos os módulos há observações, situação, autoria, cadastro, alteração e versão. O campo Segurança/Prevenção foi substituído pela identificação do usuário conectado para o lançamento. Nesta versão, não existem campos separados para o segurança de saída e o segurança de retorno: a auditoria registra quem realizou a atualização, e o recebedor pode ser informado onde previsto. O módulo Veículos não possui um motorista de retorno separado; caso diferente do motorista da retirada, informe em observações.

O app inicia sem os nomes, documentos, placas e demais registros pessoais da planilha. Uma migração do histórico XLSB exige transformação para o formato JSON aceito e revisão de datas Excel, documentos com zeros à esquerda, duplicidades e células calculadas. O programa não importa XLSB diretamente.
