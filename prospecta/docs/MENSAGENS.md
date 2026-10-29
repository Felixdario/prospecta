# Guia de mensagens

O porquê de cada escolha (com fontes) está em [ABORDAGEM.md](ABORDAGEM.md). Aqui ficam as regras e
os textos que o sistema gera.

## A mensagem que já funcionou, e o que mudou

> "Boa tarde, tudo certo? Me chamo Eduardo Felix, trabalho com venda de sites há mais de 3 anos e
> reparei que sua empresa não tem um site próprio, eu já fiz um site e gostaria de te apresentar sem
> compromisso, gostaria de perguntar se tem algum horário hoje para conversarmos sobre isso."

**O que ela acerta:** observação concreta (não tem site), algo pronto para mostrar ("já fiz um site")
e "sem compromisso".

| Antes | Agora | Por quê |
|---|---|---|
| Começa com "Me chamo…" | Começa pela empresa: "Vi a Academia X no Google: nota 4,8 com 212 avaliações, parabéns pelo trabalho!" | Relevância é o que faz alguém responder |
| Uma frase longa | Frases curtas, ~350 caracteres no WhatsApp e no Instagram | Lida no celular, em segundos |
| "Algum horário hoje para conversarmos?" | "Posso te mandar uma ideia de como ficaria o site de vocês? Sem compromisso." | Pedir interesse é mais fácil de responder do que marcar conversa |
| "Já fiz um site" (sempre) | Só quando você marca "Já preparei uma prévia": "Montei uma prévia… Posso te mandar o link?" | Não afirmar o que não foi feito; e não mandar link sem permissão |
| Um único texto para tudo | Um texto para cada canal: WhatsApp, Instagram, e-mail (com assunto e descadastro), formulário e roteiro de ligação | Cada canal tem tamanho e formato próprios |

## Regras que o sistema aplica

1. Só cita fatos verificados (nome, nota, avaliações, ausência de site no perfil, problemas confirmados no site).
2. Nunca diz que a empresa perde clientes ou dinheiro, nunca promete resultado, não usa urgência.
3. Se a empresa tem site, não diz que não tem e não chama o site de ruim: cita no máximo um ponto verificado
   (dois no e-mail).
4. A variação precisa combinar com os dados (ex.: "sem site" é recusada para quem tem site próprio).
5. O verificador **bloqueia**: "perdendo clientes", "garanto", "100%", "dobrar as vendas", "última chance",
   "urgente", "site ruim/feio", "seus concorrentes já…", nota diferente da real, campos `[ ]` não preenchidos.
6. O verificador **avisa**: primeira mensagem curta com mais de 450 caracteres, começar com "Meu nome é",
   link na primeira mensagem, e-mail sem a frase de descadastro, e-mail com mais de 170 palavras,
   excesso de exclamações e ausência de site vinda de planilha.
7. Com IA ligada, o texto da IA passa pelo mesmo verificador; se falhar, o sistema usa o modelo e mostra o motivo.

## Exemplos gerados pelo sistema

Empresas fictícias, geradas à tarde (a saudação do roteiro muda com o horário). Se você informar o
nome do responsável, a mensagem o chama pelo primeiro nome.

### Empresa sem site (WhatsApp ou Direct do Instagram)

`sem_site` · canal: whatsapp · 366 caracteres

> Oi, tudo bem? Vi a Academia Força Total no Google: nota 4,8 com 212 avaliações, parabéns pelo trabalho! Reparei que vocês ainda não têm um site próprio. Sou o Eduardo e faço sites para negócios locais há mais de 3 anos. Um site poderia ajudar a apresentar os planos, horários e modalidades. Posso te mandar uma ideia de como ficaria o site de vocês? Sem compromisso.

### Só tem Instagram no perfil do Google

`presenca_limitada` · canal: instagram · 433 caracteres

> Oi, tudo bem? Vi a Academia Força Total no Google: nota 4,8 com 212 avaliações, parabéns pelo trabalho! Reparei que o perfil no Google leva para o Instagram e não para um site próprio. Sou o Eduardo e faço sites para negócios locais há mais de 3 anos. Um site próprio poderia complementar o Instagram e ajudar a apresentar os planos, horários e modalidades. Posso te mandar uma ideia de como ficaria o site de vocês? Sem compromisso.

### Site com pontos de melhoria verificados

`site_desatualizado` · canal: whatsapp · 415 caracteres

> Oi, tudo bem? Vi a Oficina Ponto Certo no Google: nota 4,6 com 143 avaliações, parabéns pelo trabalho! Dei uma olhada no site e notei que não há um botão direto para WhatsApp ou telefone na página inicial. Sou o Eduardo e faço sites para negócios locais há mais de 3 anos. Um site poderia ajudar a apresentar os serviços e as especialidades da oficina. Posso te mandar 2 ou 3 sugestões de melhoria? Sem compromisso.

### Empresa sem site, por e-mail

`sem_site` · canal: email · 538 caracteres

```
Assunto: Site para a Academia Força Total

Olá, tudo bem?

Vi a Academia Força Total no Google: nota 4,8 com 212 avaliações, parabéns pelo trabalho!

Reparei que vocês ainda não têm um site próprio. Um site poderia ajudar a apresentar os planos, horários e modalidades e facilitar o contato de quem quer agendar uma aula experimental.

Sou o Eduardo e faço sites para negócios locais há mais de 3 anos. Posso te mandar uma ideia de como ficaria o site de vocês? Sem compromisso.

Eduardo Felix

Se não quiser receber outros e-mails meus, é só responder "não" que eu não envio mais.
```

### Abertura curta (quando não sabe quem atende)

`abertura_curta` · canal: whatsapp · 180 caracteres

> Oi, tudo bem? Falo com o responsável pela Academia Força Total? Sou o Eduardo e faço sites para negócios locais. Tive uma ideia para a presença de vocês no Google, posso te contar?

### Roteiro de ligação (pedir permissão)

`roteiro_ligacao` · canal: ligacao · 677 caracteres

```
Roteiro de ligação. Objetivo: conseguir permissão e o melhor contato, não vender por telefone.
1. "Boa tarde! Aqui é o Eduardo. Falo com o responsável pela Academia Força Total?" Se não for: "Com quem eu falo sobre a divulgação de vocês, e qual o melhor horário?"
2. "Vou ser rápido: vi vocês no Google (nota 4,8, parabéns!) e não encontrei um site próprio de vocês. Eu faço sites para negócios locais."
3. "Posso te mandar uma ideia de como ficaria o site de vocês? Qual o melhor WhatsApp ou e-mail?"
4. Anote o WhatsApp ou e-mail no Prospecta e clique em "Registrar que autorizou contato".
Se não houver interesse: agradeça, registre como "Sem interesse" e não ligue de novo.
```

### Follow-up com proposta concreta (2º contato)

`follow_up` · canal: whatsapp · 267 caracteres

> Oi, tudo bem? Voltando à minha mensagem: a ideia é um site simples para vocês, com planos, horários, modalidades, localização e canais de contato, ligado ao perfil do Google e com botão de WhatsApp. Quer que eu te mande um exemplo? Se não for o momento, sem problema.

### Último contato (encerramento educado)

`follow_up_final` · canal: whatsapp · 145 caracteres

> Oi, tudo bem? Vou parar de mandar mensagem por aqui para não incomodar. Se em algum momento quiserem um site, é só me chamar. Sucesso para vocês!

### Com prévia pronta

`sem_site` · canal: whatsapp · 371 caracteres

> Oi, tudo bem? Vi a Academia Força Total no Google: nota 4,8 com 212 avaliações, parabéns pelo trabalho! Reparei que vocês ainda não têm um site próprio. Sou o Eduardo e faço sites para negócios locais há mais de 3 anos. Um site poderia ajudar a apresentar os planos, horários e modalidades. Montei uma prévia de como poderia ficar o site de vocês. Posso te mandar o link?

### EUA: roteiro de ligação

`roteiro_ligacao` · canal: ligacao · 778 caracteres

```
Roteiro de ligação em inglês. Objetivo: conseguir permissão e o melhor contato, não vender por telefone.
1. "Hi, this is Eduardo. Am I speaking with the owner or manager of Sunrise Dental?" Se não for: "Who would be the best person to talk to about your marketing, and when's a good time to reach them?"
2. "I'll be quick: I came across you on Google and saw your 4.8-star rating. I couldn't find a website for your business. I build websites for local businesses."
3. "Would it be okay if I sent you an idea of what your site could look like? What's the best email for that?"
4. Anote o e-mail no Prospecta e clique em "Registrar que autorizou contato".
Se não houver interesse: agradeça ("No problem, thanks for your time!"), registre como "Sem interesse" e não ligue de novo.
```

### EUA: e-mail para empresa sem site (com endereço configurado)

`sem_site` · canal: email · 605 caracteres

```
Assunto: Website for Sunrise Dental

Hi, hope you're doing well.

I came across Sunrise Dental on Google: 4.8 stars from 212 reviews, great work!

I couldn't find a website linked to your profile. A simple website could help present your services better and make it easier for customers to reach you.

I'm Eduardo and I've been building websites for local businesses for over 3 years. Would it help if I sent you an idea of what yours could look like?

Eduardo Felix
Rua Exemplo, 100 - Curitiba, PR, Brasil

This email is a business proposal for website services. If you'd rather not hear from me, just reply "no" and I won't email you again.
```

## Respostas (depois que a empresa respondeu)

As variações "Respondeu demonstrando interesse", "Pediu mais informações", "Pediu contato em outro
horário" e "Não deseja receber novas mensagens" continuam disponíveis na lista de situações. A de
"mais informações" inclui o link do seu portfólio quando ele está em Configurações.

## Dicas de uso

- Revise sempre. Uma frase sua sobre algo específico da empresa (um serviço que chamou atenção,
  uma foto do Instagram) deixa a mensagem ainda mais natural.
- Use o canal recomendado. Se o WhatsApp avisar que o número não existe, clique em "Não tem WhatsApp".
- No máximo 2 retornos, com pelo menos 3 dias entre eles.
- Preencha em Configurações → Seu perfil: nome, experiência, WhatsApp e portfólio (vão na assinatura
  do e-mail) e, para e-mails aos EUA e Canadá, o endereço comercial.

## Inglês (EUA, Canadá, Reino Unido, Austrália)

As mensagens em inglês seguem as mesmas regras e são escritas para pequenos negócios (não são
traduções literais). Nos EUA e no Canadá o primeiro contato sugerido é a ligação; no Reino Unido e na
Austrália, ligação ou formulário do site. E-mails em inglês saem identificados como proposta comercial,
com descadastro e, quando configurado, seu endereço postal (CAN-SPAM). Veja docs/CONFORMIDADE.md.
