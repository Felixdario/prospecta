# Guia de mensagens

## A mensagem que já funcionou

> "Boa tarde, tudo certo? Me chamo Eduardo Felix, trabalho com venda de sites há mais de 3 anos e
> reparei que sua empresa não tem um site próprio, eu já fiz um site e gostaria de te apresentar sem
> compromisso, gostaria de perguntar se tem algum horário hoje para conversarmos sobre isso."

**O que ela acerta:** cumprimento natural, apresentação com experiência, uma observação concreta
(não tem site), algo pronto para mostrar ("já fiz um site") e "sem compromisso".

**O que dá para melhorar:**

| Ponto | Ajuste nos modelos |
|---|---|
| Frase repetida e uma única oração longa | Frases curtas, uma ideia por frase |
| "Venda de sites" soa como vendedor | "Trabalho com desenvolvimento de sites para empresas" |
| Não mostra que pesquisou *esta* empresa | Cita o nome e, quando a reputação é boa, a nota e o número de avaliações (dados verificados) |
| Não diz como um site ajudaria | Um benefício típico do segmento (academia: planos, horários, aula experimental) |
| "Algum horário hoje" pressiona | Pergunta simples: "Você é a pessoa responsável por essa parte?" |
| "Já fiz um site" só é verdade quando você fez | O sistema só menciona a prévia quando você marca "Já preparei uma prévia" |

## Regras que o sistema aplica

1. Só cita fatos verificados (nome, nota, avaliações, ausência de site no perfil, problemas confirmados no site).
2. Nunca diz que a empresa perde clientes ou dinheiro, nunca promete resultado, não usa urgência.
3. Se a empresa tem site, não diz que não tem e não chama o site de ruim: cita no máximo dois pontos verificados.
4. A variação precisa combinar com os dados (ex.: "sem site" é recusada para quem tem site próprio).
5. O verificador bloqueia: "perdendo clientes", "garanto", "100%", "dobrar as vendas", "última chance",
   "urgente", "site ruim/feio", "seus concorrentes já…", nota diferente da real, campos `[ ]` não preenchidos.
   Avisa (sem bloquear) sobre mensagens longas, excesso de exclamações e ausência de site vinda de planilha.
6. Com IA ligada, o texto da IA passa pelo mesmo verificador; se falhar, o sistema usa o modelo e mostra o motivo.

## As variações (exemplos gerados pelo próprio sistema)

Exemplos para uma academia fictícia com nota 4,8 e 212 avaliações, gerados à tarde. A saudação
muda conforme o horário (bom dia, boa tarde, boa noite) e, se você informar o responsável, a
mensagem o chama pelo primeiro nome.

### Empresa sem site identificado

`sem_site`

> Boa tarde, tudo bem? Meu nome é Eduardo e trabalho com desenvolvimento de sites para empresas há mais de 3 anos. Encontrei a Academia Força Total no Google Maps. Vi que vocês têm nota 4,8 com 212 avaliações, um ótimo sinal do trabalho de vocês. Procurei e não encontrei um site próprio vinculado ao perfil de vocês. Um site simples poderia ajudar a apresentar os planos, horários e modalidades e facilitar o contato de quem quer agendar uma aula experimental. Você é a pessoa responsável por essa parte? Se fizer sentido, posso te apresentar uma proposta sem compromisso.

### Presença digital limitada (rede social, link ou plataforma)

`presenca_limitada`

> Boa tarde, tudo bem? Meu nome é Eduardo e trabalho com desenvolvimento de sites para empresas há mais de 3 anos. Encontrei a Academia Força Total no Google Maps. Vi que vocês têm nota 4,8 com 212 avaliações, um ótimo sinal do trabalho de vocês. O perfil de vocês direciona para o Instagram, mas não encontrei um site próprio. Um site próprio poderia complementar o que vocês já fazem nas redes, ajudando a apresentar os planos, horários e modalidades e facilitar o contato de quem quer agendar uma aula experimental. Você é a pessoa responsável por essa parte? Se fizer sentido, posso te apresentar uma proposta sem compromisso.

### Site com oportunidades de melhoria verificadas

`site_desatualizado`

> Boa tarde, tudo bem? Meu nome é Eduardo e trabalho com desenvolvimento de sites para empresas há mais de 3 anos. Encontrei a Oficina Ponto Certo no Google Maps. Vi que vocês têm nota 4,6 com 143 avaliações, um ótimo sinal do trabalho de vocês. Dei uma olhada no site de vocês e notei que a página não está configurada para se adaptar ao celular e que não há um botão direto para WhatsApp ou telefone na página inicial. Tenho algumas ideias de melhorias que poderiam ajudar a apresentar os serviços e as especialidades da oficina e facilitar pedidos de orçamento. Você é a pessoa responsável por essa parte? Se fizer sentido, posso te apresentar uma proposta sem compromisso.

### Site próprio sem problemas evidentes

`site_existente`

> Boa tarde, tudo bem? Meu nome é Eduardo e trabalho com desenvolvimento de sites para empresas há mais de 3 anos. Encontrei a Academia Força Total no Google Maps. Vi o site de vocês. Além de criar sites, também faço novas versões e melhorias. Se em algum momento vocês pensarem em atualizar ou ampliar o site, posso ajudar. Faz sentido conversarmos rapidamente?

### Responsável ainda não identificado

`responsavel_nao_identificado`

> Boa tarde, tudo bem? Meu nome é Eduardo e trabalho com desenvolvimento de sites para empresas há mais de 3 anos. Encontrei a Academia Força Total no Google Maps. Gostaria de falar com a pessoa responsável pela divulgação da empresa sobre uma ideia de site. Poderia me indicar com quem posso conversar, por favor?

### Follow-up único (sem resposta)

`follow_up`

> Boa tarde, tudo bem? Passando só para retomar minha mensagem anterior sobre um site para a Academia Força Total. Se não for o momento, sem problema, é só me avisar que não volto a insistir. Se tiver interesse, posso te mostrar a ideia em poucos minutos.

### Respondeu demonstrando interesse

`resposta_interesse`

> Que bom, obrigado pelo retorno! Para eu preparar algo alinhado com a Academia Força Total, posso te fazer três perguntas rápidas? 1) O que vocês mais gostariam que o site mostrasse (por exemplo: planos, horários, modalidades, localização e canais de contato)? 2) Vocês já têm um domínio, como www.nomedaempresa.com.br? 3) Qual o melhor dia e horário para conversarmos por uns 15 minutos?

### Pediu mais informações

`pedido_informacoes`

> Claro! Funciona assim: eu crio um site profissional para a Academia Força Total, adaptado para celular, com planos, horários, modalidades, localização e canais de contato. Antes de falar em valores, entendo o que vocês precisam e apresento uma proposta com prazo e investimento. Posso te enviar alguns exemplos de trabalhos que já fiz? Se preferir, também podemos conversar por telefone.

### Pediu contato em outro horário

`outro_horario`

> Sem problema, obrigado por avisar! Qual dia e horário ficam melhores para você? Retorno no horário que você preferir.

### Não deseja receber novas mensagens

`opt_out`

> Entendido, obrigado pelo retorno! Não vou mais enviar mensagens. Se no futuro precisar de algo relacionado a site, fico à disposição. Tenha um ótimo dia!

### Com prévia pronta (você marcou que já preparou)

> Boa tarde, tudo bem? Meu nome é Eduardo e trabalho com desenvolvimento de sites para empresas há mais de 3 anos. Encontrei a Academia Força Total no Google Maps. Vi que vocês têm nota 4,8 com 212 avaliações, um ótimo sinal do trabalho de vocês. Procurei e não encontrei um site próprio vinculado ao perfil de vocês. Um site simples poderia ajudar a apresentar os planos, horários e modalidades e facilitar o contato de quem quer agendar uma aula experimental. Inclusive, preparei uma prévia de como poderia ficar a página da Academia Força Total. Posso te mostrar? É sem compromisso.

## Dicas de uso

- Revise sempre. O modelo é um ponto de partida; uma frase sua sobre algo específico da empresa
  (uma foto do Instagram, um serviço que chamou atenção) aumenta muito a naturalidade.
- Preparar uma prévia antes do contato (como você já fazia) costuma ser o diferencial. Marque
  "Já preparei uma prévia" e informe o link: a mensagem passa a oferecer mostrar a prévia.
- Um único follow-up, depois de pelo menos 3 dias. Sem resposta, encerre como "Sem interesse".
- Ajuste seu nome, experiência e empresa em Configurações → Seu perfil nas mensagens.
