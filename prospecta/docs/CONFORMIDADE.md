# Conformidade: LGPD, Google e WhatsApp

> Este documento explica as decisões técnicas tomadas para respeitar a lei e as regras das
> plataformas. Não é aconselhamento jurídico. Para uso em escala, valide com um advogado.

## LGPD

**Há dado pessoal aqui?** Sim, em parte. O telefone de uma empresa pode ser o celular pessoal do
dono (muito comum em MEI e pequenos negócios), e o nome do responsável, quando você o registra,
é dado pessoal. Por isso o sistema trata esses campos com cuidado.

**Base legal provável:** legítimo interesse (art. 7º, IX), para oferecer um serviço a empresas a
partir de informações que elas mesmas tornaram públicas para contato comercial. A ANPD publicou em
fevereiro de 2024 um guia sobre o tema que orienta fazer e documentar um **teste de balanceamento**
antes de usar essa base ([resumo do guia](https://www.bmalaw.com.br/conteudo/direito-digital-protecao-de-dados-e-cybersecurity/artigos-e-noticias/o-legitimo-interesse-na-visao-da-anpd/pdf)).
Um rascunho do teste está no fim deste documento.

### O que o sistema faz

| Princípio | Implementação |
|---|---|
| Minimização | Coleta só dados comerciais (nome, categoria, endereço, telefone, site, nota, horário). **Não** coleta e-mails, textos de avaliações nem dados de quem avaliou. E-mails de planilhas importadas são descartados |
| Finalidade | Os dados são usados só para qualificar e abordar a empresa sobre criação de sites |
| Transparência | O histórico registra a origem de cada lead (Google Maps, planilha ou cadastro manual) e a data da coleta, para você responder "como conseguiu meu número?" |
| Direito de oposição | "Pediu para não receber mensagens" ou "Não contatar novamente" bloqueiam o contato na hora e colocam telefone e `place_id` na lista de supressão |
| Eliminação | "Excluir dados" apaga o lead, o histórico e as tarefas. O telefone fica só na lista de supressão, para a empresa não voltar a ser coletada nem contatada (registro necessário para cumprir o próprio pedido) |
| Segurança | Painel e API exigem token; tokens de integração são guardados como hash; escopos limitam o que cada integração faz; servidor ligado só em `127.0.0.1` por padrão; cabeçalhos de segurança; proteção contra SSRF na análise de sites |
| Prestação de contas | Registro de operações (auditoria) de alterações e de todas as chamadas feitas por integrações |
| Retenção | Dados do Google expiram em 30 dias (configurável). Registros de auditoria são apagados após 180 dias |

### Boas práticas na abordagem

- Contato individual, revisado por você, nunca em massa.
- Na primeira mensagem, diga quem você é e por que está falando com a empresa (os modelos já fazem isso).
- Ao primeiro "não tenho interesse" ou "não me mande mais mensagens", registre o opt-out. O sistema impede novos contatos.
- Se perguntarem de onde veio o número: "Do perfil público da empresa no Google Maps."

## Google Places API

| Regra | Como o sistema cumpre |
|---|---|
| Usar a API oficial e respeitar os termos | Usa apenas a Places API (New), com chave do próprio usuário. Nada de raspagem |
| Não guardar conteúdo do Google além do permitido. O `place_id` pode ser guardado sem prazo ([políticas da Places API](https://developers.google.com/maps/documentation/places/web-service/policies)); latitude/longitude, por até 30 dias ([termos específicos, seção Places](https://cloud.google.com/archive/maps-platform/terms/maps-service-terms-20250501)) | Guarda o `place_id` permanentemente. **Não** guarda coordenadas. Os demais campos guardam a data da coleta e, após `GOOGLE_CACHE_DAYS` (30), são atualizados pela API (leads em andamento) ou apagados (os demais), mantendo `place_id`, histórico e suas anotações. Comando: `python -m app.cli google-cache refresh` |
| Atribuição ao exibir dados do Google | O painel indica "Fonte: Google Maps" e oferece o link oficial do lugar (`googleMapsUri`). Para uso público ou comercial do painel por terceiros, aplique o logotipo conforme as diretrizes de atribuição do Google |
| Não exibir avaliações sem crédito ao autor | O sistema não coleta nem exibe textos de avaliações |
| Custos sob controle | Teto mensal configurável de chamadas; a pesquisa para quando o teto é atingido |

**Exportação para CSV:** os dados exportados continuam sujeitos às mesmas regras. Use a planilha para
o seu trabalho do dia a dia, não para revenda ou para formar uma base permanente.

## WhatsApp

**Envio manual com link `wa.me` (o que o sistema faz):** o link oficial "clique para conversar" abre a
conversa com o texto preenchido no seu WhatsApp. O envio é seu, uma conversa por vez. Mesmo assim, os
termos do WhatsApp proíbem mensagens em massa, automatizadas ou não solicitadas que gerem denúncias, e
contas denunciadas podem ser restringidas. Por isso o sistema impõe:

- limite diário de contatos (padrão 20);
- intervalo mínimo entre tentativas sem resposta (padrão 3 dias);
- no máximo 2 tentativas sem resposta;
- bloqueio imediato após opt-out e lista de supressão;
- bloqueio de telefone já contatado por outro cadastro (duplicatas);
- aviso fora do horário comercial.

**WhatsApp Business Platform (API oficial):** permite envio automatizado, mas exige que a pessoa tenha
**dado opt-in prévio**, autorizando expressamente mensagens daquela empresa ([documentação da Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in)).
Telefone público não é opt-in. Portanto, a API oficial **não serve para o primeiro contato frio**. Ela
pode fazer sentido depois, para quem respondeu e autorizou. O sistema já registra consentimento
("Registrar que autorizou contato"), base para uma integração futura. A integração em si **não foi
implementada**.

## Rascunho de teste de balanceamento (legítimo interesse)

| Pergunta | Resposta para este caso |
|---|---|
| Qual o interesse? | Oferecer serviço de criação de sites a empresas locais (atividade comercial lícita) |
| O tratamento é necessário? | Sim: para oferecer o serviço é preciso identificar empresas e um canal de contato comercial |
| Há meio menos invasivo? | Os dados usados são os mínimos (dados públicos de contato comercial); e-mails e avaliações não são coletados |
| A empresa espera esse contato? | É razoável: o telefone foi publicado no perfil comercial para receber contatos |
| Quais os riscos ao titular? | Incômodo com mensagens indesejadas. Mitigado por contato individual, limites de frequência e opt-out imediato e permanente |
| Salvaguardas | Transparência sobre a origem, oposição a qualquer momento, retenção limitada, segurança de acesso, auditoria |

Revise e guarde este teste com data; refaça se mudar a forma de abordagem (ex.: começar a usar e-mail).
