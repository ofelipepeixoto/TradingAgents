# Radar de Teses e Riscos · laboratório 0.1.0

O operador fornece trechos de fontes, recebe uma análise em português e revisa
fontes, afirmações e riscos antes de exportar. A demonstração é fictícia e custa zero.

Este fork preserva a licença Apache 2.0, o histórico e a autoria da TauricResearch.
A pasta `radar_lab/` é uma extensão autoral isolada, inspirada na separação entre
analistas, contrapontos e risco do TradingAgents. A primeira versão usa uma única
geração estruturada em vez do grafo completo: facilita medir qualidade e limitar
custo. Os comandos originais `tradingagents` continuam independentes e **não são
protegidos pelos limites deste laboratório**.

## Começar com o exemplo sem API

Requer Python 3.11 ou superior. Na raiz do clone, sem instalar dependências:

```bash
python -m radar_lab demo
```

O comando mostra ID, hash, status `PENDING_REVIEW` e caminho de uma prévia HTML
local. Abra a prévia para ler. O exemplo contém a empresa fictícia Aurora e URLs
de demonstração em `example.org`. Não representa empresa, evento ou recomendação real.

Para ver o relatório no terminal:

```bash
python -m radar_lab show ID_DA_EXECUCAO
```

## Revisar e exportar

Confira se as fontes existem e são adequadas, se cada afirmação é sustentada pelo
trecho citado, e se riscos e lacunas estão explícitos. A validação automática só
confirma o formato e os IDs: **não comprova que uma fonte sustenta uma afirmação**.

Depois de ler a versão correspondente ao hash:

```bash
python -m radar_lab review ID_DA_EXECUCAO \
  --hash HASH_DO_RELATORIO \
  --reviewer "Nome do revisor" \
  --decision approve \
  --checked-sources --checked-claims --checked-risks \
  --note "Descreva o que foi conferido e as limitações aceitas."

python -m radar_lab export ID_DA_EXECUCAO
```

Para rejeitar, use `--decision reject --note "Motivo da rejeição"` com ID, hash e
revisor. Rejeição e aprovação são finais para aquela execução. Corrija as
evidências e gere outra análise quando necessário. Aprovação expira em 24 horas
e autoriza apenas exportar Markdown local. Nenhum comando publica ou envia ordens.
O relatório demo mantém sua marca de dados fictícios mesmo depois da revisão.

## Modo com OpenAI — ativação manual

O código do adaptador está disponível, mas precisa de homologação com API real.
Os testes automatizados usam transporte simulado. Nesta entrega nenhuma chave
foi configurada, nenhum dado real foi enviado e nenhuma geração paga foi feita.

1. Prepare um JSON de evidências no formato de
   [evidence.example.json](../../examples/radar-lab/evidence.example.json).
   Substitua os exemplos por trechos que você pode enviar à OpenAI e defina
   `is_demo` como `false`. O laboratório não visita URLs ou coleta notícias.
2. Prepare um arquivo privado de tarifas a partir de
   [pricing.template.json](../../examples/radar-lab/pricing.template.json).
   Informe o ID do modelo, preços em USD por milhão de tokens e a data em que
   conferiu a [página oficial](https://openai.com/api/pricing/). O template é
   deliberadamente inválido; nenhuma tarifa comercial é presumida.
3. Configure `OPENAI_API_KEY` no ambiente de execução por um mecanismo seguro.
   Não cole a chave no chat, em arquivos do projeto ou em argumentos de comando.
4. Execute somente depois de confirmar o envio das evidências e os custos:

```bash
python -m radar_lab analyze \
  --evidence /caminho/privado/evidencias.json \
  --pricing /caminho/privado/tarifas.json \
  --live --run-limit-usd 0.50 --day-limit-usd 2.00 \
  --max-output-tokens 3000
```

Se o pacote original estiver instalado, `radar-teses` oferece os mesmos comandos.
O caminho sem instalação (`python -m radar_lab`) é o mais simples para o demo.

## Como os limites funcionam

| Controle | Comportamento |
|---|---|
| Gerações | Uma por execução, sem ferramentas e sem tentativas automáticas |
| Pré-verificação | A API conta tokens do mesmo conteúdo e esquema antes da geração |
| Entrada | Até 12 fontes, 64 KiB por arquivo, 48 KiB de evidências, 20.000 tokens |
| Saída | Padrão 3.000; intervalo permitido de 256 a 8.000, incluindo raciocínio |
| Custo por execução | Padrão USD 0,50; bloqueio antes da geração se reserva exceder |
| Custo diário | Padrão USD 2,00; reserva atômica em SQLite, dia de São Paulo |
| Tarifas | Modelo explícito, valores positivos e revisão de até 7 dias |
| API | Endpoint oficial fixo, HTTPS, sem proxies do ambiente ou redirecionamentos |
| Falha ou timeout | Reserva mantida; não é presumido que a chamada foi gratuita |
| Aprovação | Identidade declarada, hash, checklist, justificativa e validade de 24h |

A reserva é `tokens de entrada × tarifa de entrada + limite de saída × tarifa de saída`,
arredondada para cima em microdólares. Descontos de cache não são presumidos.
Reservas não são devolvidas, mesmo quando o consumo real é menor. O total diário
é conservador e persiste após reiniciar o processo. A primeira chamada paga fixa
o teto diário; o processo rejeita mudanças desse teto no mesmo dia e diretório.

O gasto registrado é calculado com as tarifas fornecidas, não extraído da fatura.
Tarifas incorretas ou alteradas pelo fornecedor podem invalidar a estimativa.
Esta proteção cobre somente este adaptador, não outras aplicações, chaves ou
custos de infraestrutura. Não constitui um limite financeiro da conta OpenAI.
Se a contagem usada exceder o contrato de tokens, a saída é bloqueada e o
desvio é contabilizado. Não há retomada automática de geração.

## Segurança e isolamento

O estado fica em `~/.radar-teses-riscos/`, separado do TradingAgents e dos outros
projetos. Use `--data-dir` **antes** do subcomando para um diretório dedicado.
Mantenha o mesmo diretório para conservar o orçamento diário. Não há isolamento
entre tenants ou identidade autenticada: é uma ferramenta de um operador local
que pode editar seu próprio banco. Não exponha essa CLI como serviço multiusuário.

Trechos ficam na mensagem de usuário, separados das instruções. Saída é validada,
IDs de fonte precisam existir e a prévia HTML escapa texto e bloqueia scripts.
Esses mecanismos reduzem a superfície de manipulação; não demonstram imunidade
semântica a prompt injection. A revisão humana continua necessária.

O processo não habilita brokers, redes sociais, Sites, Supabase ou publicação.
Nenhuma aprovação local concede essas permissões. Dados e relatórios são locais;
no modo `--live`, as evidências e o esquema são enviados à OpenAI tanto na
contagem quanto na geração. `store=false` não altera por si só a política de
retenção do provedor. O transporte não permite servidores alternativos.

## Verificação e evolução

```bash
python -m pip install 'pytest==9.1.1' 'ruff==0.16.9'
python -m pytest -q -c /dev/null lab_tests
python -m ruff check radar_lab lab_tests
```

Os testes cobrem estouro de orçamento, concorrência, persistência, falhas,
ausência de chave, citações inválidas, recusas, aprovação expirada, alteração do
relatório e escapes de HTML. Os testes de papéis de mensagem não são um
benchmark de resistência de modelos. O CI do laboratório executa sem APIs ou
dependências do grafo original. O CI original continua cobrindo o pacote completo.

Próxima homologação: um pequeno conjunto de fontes reais com avaliação de
fidelidade, omissões, utilidade, latência e custo. Comparar o fluxo único com o
grafo TradingAgents antes de aumentar agentes. API multiusuário, interface com
seleções, banco remoto e coleta automática são evoluções posteriores.

Referências do contrato de API consultadas em 01/10/2026:
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
e [contagem de tokens](https://developers.openai.com/api/docs/guides/token-counting).
