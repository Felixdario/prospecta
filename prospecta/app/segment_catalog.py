"""Lista de segmentos para o seletor da pesquisa.

Cada item tem o termo de busca em português (Brasil) e em inglês (demais países). O termo é o que
vai para o Google, então precisa ser como as pessoas pesquisam ("academias", "dentists").
Itens sem tradução (None) só aparecem no idioma que têm.
"""
from __future__ import annotations

# (grupo, rótulo do grupo, [(id, termo em português, termo em inglês)])
CATALOG: list[tuple[str, str, list[tuple[str, str | None, str | None]]]] = [
    ("academia", "Academias e esportes", [
        ("academias", "Academias", "gyms"),
        ("pilates", "Estúdios de pilates", "pilates studios"),
        ("crossfit", "Boxes de crossfit", "crossfit gyms"),
        ("yoga", "Estúdios de yoga", "yoga studios"),
        ("artes_marciais", "Escolas de artes marciais", "martial arts schools"),
        ("natacao", "Escolas de natação", "swim schools"),
        ("personal", "Personal trainers", "personal trainers"),
    ]),
    ("saude", "Saúde", [
        ("dentistas", "Dentistas", "dentists"),
        ("clinicas", "Clínicas médicas", "medical clinics"),
        ("fisioterapia", "Clínicas de fisioterapia", "physical therapists"),
        ("psicologos", "Psicólogos", "psychologists"),
        ("nutricionistas", "Nutricionistas", "nutritionists"),
        ("estetica", "Clínicas de estética", "med spas"),
        ("dermatologistas", "Dermatologistas", "dermatologists"),
        ("quiropraxia", "Quiropraxia", "chiropractors"),
        ("fonoaudiologia", "Fonoaudiólogos", "speech therapists"),
        ("veterinarios", "Clínicas veterinárias", "veterinarians"),
    ]),
    ("beleza", "Beleza", [
        ("saloes", "Salões de beleza", "hair salons"),
        ("barbearias", "Barbearias", "barbershops"),
        ("esmalterias", "Esmalterias e manicures", "nail salons"),
        ("sobrancelhas", "Design de sobrancelhas e cílios", "lash and brow studios"),
        ("tatuagem", "Estúdios de tatuagem", "tattoo shops"),
        ("spas", "Spas", "day spas"),
        ("depilacao", "Depilação", "waxing studios"),
        ("maquiadores", "Maquiadores", "makeup artists"),
    ]),
    ("alimentacao", "Alimentação", [
        ("restaurantes", "Restaurantes", "restaurants"),
        ("pizzarias", "Pizzarias", "pizza places"),
        ("hamburguerias", "Hamburguerias", "burger restaurants"),
        ("cafeterias", "Cafeterias", "coffee shops"),
        ("padarias", "Padarias", "bakeries"),
        ("confeitarias", "Confeitarias e docerias", "cake shops"),
        ("sorveterias", "Sorveterias", "ice cream shops"),
        ("lanchonetes", "Lanchonetes", "sandwich shops"),
        ("bares", "Bares", "bars"),
        ("food_trucks", "Food trucks", "food trucks"),
        ("buffets", "Buffets", "catering services"),
        ("marmitarias", "Marmitarias", "meal prep services"),
        ("acaiterias", "Açaiterias", None),
    ]),
    ("automotivo", "Automotivo", [
        ("oficinas", "Oficinas mecânicas", "auto repair shops"),
        ("funilaria", "Funilaria e pintura", "auto body shops"),
        ("lava_jatos", "Lava-jatos", "car washes"),
        ("estetica_auto", "Estética automotiva", "auto detailing"),
        ("pneus", "Borracharias e pneus", "tire shops"),
        ("autoeletricas", "Autoelétricas", "auto electrical repair"),
        ("guinchos", "Guinchos", "towing services"),
    ]),
    ("profissionais", "Serviços profissionais", [
        ("advocacia", "Escritórios de advocacia", "law firms"),
        ("contabilidade", "Escritórios de contabilidade", "accountants"),
        ("imobiliarias", "Imobiliárias", "real estate agencies"),
        ("seguros", "Corretoras de seguros", "insurance agencies"),
        ("arquitetura", "Escritórios de arquitetura", "architects"),
        ("engenharia", "Empresas de engenharia", "engineering firms"),
        ("consultorias", "Consultorias", "consulting firms"),
        ("despachantes", "Despachantes", None),
    ]),
    ("educacao", "Educação", [
        ("idiomas", "Escolas de idiomas", "language schools"),
        ("autoescolas", "Autoescolas", "driving schools"),
        ("musica", "Escolas de música", "music schools"),
        ("danca", "Escolas de dança", "dance studios"),
        ("reforco", "Reforço escolar", "tutoring centers"),
        ("creches", "Creches e berçários", "daycares"),
        ("escolas", "Escolas particulares", "private schools"),
        ("cursos", "Cursos profissionalizantes", "vocational schools"),
    ]),
    ("pet", "Pets", [
        ("pet_shops", "Pet shops", "pet stores"),
        ("banho_tosa", "Banho e tosa", "dog groomers"),
        ("hotel_pet", "Hotéis para cães", "dog boarding"),
        ("adestradores", "Adestradores", "dog trainers"),
    ]),
    ("varejo", "Lojas", [
        ("roupas", "Lojas de roupas", "clothing boutiques"),
        ("oticas", "Óticas", "optical stores"),
        ("calcados", "Lojas de calçados", "shoe stores"),
        ("floriculturas", "Floriculturas", "florists"),
        ("moveis", "Lojas de móveis", "furniture stores"),
        ("construcao", "Materiais de construção", "hardware stores"),
        ("joalherias", "Joalherias", "jewelry stores"),
        ("presentes", "Lojas de presentes", "gift shops"),
        ("cosmeticos", "Lojas de cosméticos", "beauty supply stores"),
        ("papelarias", "Papelarias", "stationery stores"),
        ("informatica", "Lojas de informática", "computer stores"),
    ]),
    ("servicos", "Serviços para casa e empresa", [
        ("eletricistas", "Eletricistas", "electricians"),
        ("encanadores", "Encanadores", "plumbers"),
        ("ar_condicionado", "Ar-condicionado", "HVAC contractors"),
        ("telhados", "Telhados e calhas", "roofing contractors"),
        ("pintores", "Pintores", "painters"),
        ("reformas", "Reformas e construção", "remodeling contractors"),
        ("limpeza", "Empresas de limpeza", "cleaning services"),
        ("dedetizadoras", "Dedetizadoras", "pest control"),
        ("paisagismo", "Paisagismo e jardinagem", "landscaping companies"),
        ("piscinas", "Manutenção de piscinas", "pool services"),
        ("chaveiros", "Chaveiros", "locksmiths"),
        ("vidracarias", "Vidraçarias", "glass shops"),
        ("marcenarias", "Marcenarias", "cabinet makers"),
        ("mudancas", "Mudanças e fretes", "movers"),
        ("fotografos", "Fotógrafos", "photographers"),
        ("eventos", "Decoração e organização de eventos", "event planners"),
        ("graficas", "Gráficas", "print shops"),
        ("celulares", "Assistência técnica de celulares", "phone repair shops"),
        ("lavanderias", "Lavanderias", "dry cleaners"),
    ]),
]


def catalog_for_api() -> list[dict]:
    return [
        {"group": key, "label": label,
         "items": [{"id": i, "pt": pt, "en": en} for i, pt, en in items]}
        for key, label, items in CATALOG
    ]
