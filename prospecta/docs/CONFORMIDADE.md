# Conformidade: LGPD, Google, WhatsApp e regras de outros países

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
| Minimização | Coleta só dados comerciais (nome, categoria, endereço, telefone, site, nota, horário) e os **canais de contato que a própria empresa publicou** no site ou na página de links: WhatsApp (link `wa.me`), Instagram e, **só no Brasil**, até 3 e-mails. **Não** coleta textos de avaliações nem dados de quem avaliou, e não procura contatos em sites de terceiros |
| Finalidade | Os dados são usados só para qualificar e abordar a empresa sobre criação de sites |
| Transparência | O histórico registra a origem de cada lead (Google Maps, planilha ou cadastro manual) e a data da coleta. Cada contato mostra de onde veio ("publicado no site", "informado por você"), para você responder "como conseguiu meu contato?" |
| Direito de oposição | "Pediu para não receber mensagens" ou "Não contatar novamente" bloqueiam o contato na hora e colocam telefone e `place_id` na lista de supressão |
| Eliminação | "Excluir dados" apaga o lead, o histórico e as tarefas. O telefone fica só na lista de supressão, para a empresa não voltar a ser coletada nem contatada (registro necessário para cumprir o próprio pedido) |
| Segurança | Painel e API exigem token; tokens de integração são guardados como hash; escopos limitam o que cada integração faz; servidor ligado só em `127.0.0.1` por padrão; cabeçalhos de segurança; proteção contra SSRF na análise de sites |
| Prestação de contas | Registro de operações (auditoria) de alterações e de todas as chamadas feitas por integrações |
| Retenção | Dados do Google expiram em 30 dias (configurável). Registros de auditoria são apagados após 180 dias |

### E-mail no Brasil

Não existe no Brasil uma lei específica de e-mail comercial como a CAN-SPAM; valem a LGPD e o
Código de Autorregulamentação para a Prática de E-mail Marketing (CAPEM, adesão voluntária). O
sistema segue o que esses textos pedem para um contato B2B de boa-fé:

- só usa e-mails **publicados pela própria empresa** no site dela (página inicial ou de contato), nunca
  listas compradas ou endereços de terceiros;
- **não guarda** os e-mails de um site que diga que não quer receber ofertas ("não aceitamos propaganda",
  "no solicitations" etc.) e mostra um aviso no lead;
- todo e-mail sai com remetente real (sua assinatura), assunto que descreve o conteúdo e a frase
  "Se não quiser receber outros e-mails meus, é só responder 'não'…";
- a resposta "não" deve ser registrada como opt-out: o e-mail e o telefone vão para a lista de supressão;
- valem os mesmos limites de frequência dos outros canais (envio um a um, pelo seu e-mail).

O sistema **não envia e-mails**: o botão "Abrir no e-mail" abre o seu programa de e-mail com o texto
preenchido, e o envio é seu.

### Instagram

O Direct do Instagram é usado manualmente (o sistema copia o texto e abre o perfil). As regras do
Instagram tratam como spam ações automatizadas em massa e mensagens comerciais repetitivas, e contas com
esse comportamento podem ser limitadas. Por isso: um contato por vez, texto revisado e personalizado, e
os mesmos limites diários. Se a pessoa não responder, não insista pelo mesmo canal mais de duas vezes.

### Boas práticas na abordagem

- Contato individual, revisado por você, nunca em massa.
- Na primeira mensagem, diga quem você é e por que está falando com a empresa (os modelos já fazem isso).
- Ao primeiro "não tenho interesse" ou "não me mande mais mensagens", registre o opt-out. O sistema impede novos contatos.
- Se perguntarem de onde veio o contato: "Do perfil público da empresa no Google Maps" ou "Do site de vocês",
  conforme a origem mostrada em "Dados da empresa".

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

> **Correção importante (28/10/2026):** os termos atuais do Google Maps Platform (última alteração em
> 26/08/2026) dizem que o cliente não pode "copiar e guardar nomes e endereços de empresas" nem exportar
> conteúdo do Google para fora do serviço (seção 3.2.3a), e só pode guardar o que os termos específicos
> permitem (3.2.3b): o `place_id` e, na Places API, coordenadas por até 30 dias (B.14.3). Ou seja, guardar
> os demais campos por 30 dias e exportá-los em CSV, como esta versão faz, **não** está coberto pelos termos.
> Para uso pessoal o risco é a suspensão da sua chave; para um produto aberto ao público, isso precisa mudar
> antes do lançamento (guardar só o `place_id` e o que é seu, e mostrar os dados do Google ao vivo).
> Fontes: [Termos](https://cloud.google.com/maps-platform/terms) e
> [Termos específicos](https://cloud.google.com/maps-platform/terms/maps-service-terms).

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

## Fora do Brasil

As regras abaixo são um resumo para orientar o uso da ferramenta, não uma análise jurídica completa.
Leis estaduais (nos EUA) e provinciais (no Canadá) podem ser mais rígidas.

### Estados Unidos

| Canal | Regra | O que o sistema faz |
|---|---|---|
| **Ligação para empresa** | A maioria das ligações feitas a uma empresa para vender a ela está isenta das regras de "Do Not Call" da FTC ([FTC, pergunta 11](https://ftc.gov/business-guidance/resources/qa-telemarketers-sellers-about-dnc-provisions-tsr-0)). Ligações automáticas ou gravadas são outra história | Sugere o **roteiro de ligação** como primeiro contato e mostra a hora local da empresa. Ligação é sempre feita por você |
| **SMS / WhatsApp para celular** | As restrições da TCPA a textos automatizados valem também para celulares de empresas, e textos de marketing por meio automatizado exigem consentimento prévio por escrito ([resumo](https://shumakerwilliams.com/business-to-business-sms-marketing-navigating-can-spam-and-tcpa-regulations/)). Vários estados têm leis próprias | Não sugere WhatsApp/SMS como primeiro contato e exibe o aviso. Nunca envia nada automaticamente |
| **E-mail** | A CAN-SPAM **vale para e-mails entre empresas**. Exige remetente verdadeiro, assunto que não engane, identificar a mensagem como anúncio, **endereço postal válido**, forma clara de descadastro e atender pedidos de descadastro em até **10 dias úteis**. Coletar endereços automaticamente ("harvesting") pode levar a penalidades maiores, inclusive criminais ([guia da FTC](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)) | **Não lê e-mails de sites fora do Brasil.** Um e-mail só entra se você cadastrar (ex.: a empresa passou na ligação). O e-mail em inglês sai identificado como proposta comercial, com descadastro e o endereço postal de Configurações; sem endereço configurado, o sistema avisa |
| **Formulário de contato do site** | Canal criado pela própria empresa para receber contatos | O diagnóstico do site indica se há formulário. As mensagens escritas em inglês (ex.: "Empresa sem site identificado") servem para colar nele |

### Canadá

A lei antispam (CASL) exige consentimento para mensagens eletrônicas comerciais (e-mail, SMS, mensagens
em redes). O consentimento implícito por "publicação visível" só vale se o próprio dono publicou o
endereço, sem aviso de que não quer receber ofertas, e se a mensagem tem relação com a função da
pessoa. O órgão regulador (CRTC) já disse que isso não é uma licença para contatar qualquer endereço
encontrado na internet ([análise de decisão do CRTC](https://www.bennettjones.com/Insights/Blogs/2016/11/CRTC-Assesses-Conspicuous-Publication-Basis-of-Implied-Consent-in-CASL-Enforcement-Decision)).
Além disso, a CASL alterou a lei de privacidade (PIPEDA) para restringir a coleta de endereços
eletrônicos por programas de computador ([Comissário de Privacidade](https://priv.gc.ca/en/privacy-topics/privacy-laws-in-canada/the-personal-information-protection-and-electronic-documents-act-pipeda/r_o_p/canada-s-anti-spam-legislation/casl-compliance-help-for-businesses/casl_tips_org)).
Por isso o sistema sugere a **ligação** como primeiro contato no Canadá e não lê e-mails dos sites.

### Reino Unido

Pelas regras de marketing eletrônico (PECR), empresas constituídas ("corporate subscribers") podem receber
e-mails comerciais sem consentimento prévio, desde que você se identifique e ofereça descadastro.
**Profissionais autônomos e algumas sociedades são tratados como pessoas físicas** e precisam ter
consentido. Na dúvida, trate como pessoa física. Para ligações, consulte antes os cadastros TPS e CTPS e
respeite quem já recusou ([ICO](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing/)).
O sistema não consulta TPS/CTPS: faça isso antes de ligar.

### Austrália

A Spam Act exige consentimento (expresso ou inferido), identificação de quem envia e opção de
descadastro em mensagens eletrônicas comerciais, e proíbe usar software de coleta de endereços e as
listas geradas por ele ([resumo](https://lawpath.com.au/blog/whats-the-spam-act-2003-cth)). O sistema
sugere ligação ou formulário do site no primeiro contato e não lê e-mails dos sites.

### Regras do Google e do WhatsApp fora do Brasil

As regras de uso da Places API (cache de 30 dias, atribuição) e do WhatsApp (opt-in para a API oficial)
são as mesmas em qualquer país.

## Rascunho de teste de balanceamento (legítimo interesse)

| Pergunta | Resposta para este caso |
|---|---|
| Qual o interesse? | Oferecer serviço de criação de sites a empresas locais (atividade comercial lícita) |
| O tratamento é necessário? | Sim: para oferecer o serviço é preciso identificar empresas e um canal de contato comercial |
| Há meio menos invasivo? | Os dados usados são os mínimos: contatos que a própria empresa publicou para receber clientes (telefone do perfil, WhatsApp e e-mail do site, Instagram). Avaliações não são coletadas |
| A empresa espera esse contato? | É razoável: os contatos foram publicados pela empresa para receber contatos; sites que pedem para não receber ofertas são respeitados |
| Quais os riscos ao titular? | Incômodo com mensagens indesejadas. Mitigado por contato individual, limites de frequência e opt-out imediato e permanente |
| Salvaguardas | Transparência sobre a origem, oposição a qualquer momento, retenção limitada, segurança de acesso, auditoria |

Revise e guarde este teste com data; refaça se mudar a forma de abordagem. (Atualizado quando o
sistema passou a usar WhatsApp, Instagram e e-mail publicados pela empresa.)
