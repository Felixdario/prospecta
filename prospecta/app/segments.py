"""Perfis de segmento: como um site pode ajudar cada tipo de negócio.

Os benefícios são HIPÓTESES genéricas do segmento (não afirmações sobre a empresa) e
alimentam as mensagens. O "valor_segmento" é uma estimativa configurável de quanto o
segmento costuma se beneficiar de um site; ele entra na pontuação como hipótese.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    keywords: tuple[str, ...]
    google_types: tuple[str, ...]
    benefits: tuple[str, str]
    site_items: str  # o que um site normalmente apresenta para esse segmento
    value: int  # 0..15, padrão; pode ser sobrescrito na configuração da pontuação


SEGMENTS: tuple[Segment, ...] = (
    Segment(
        "academia", "Academias e estúdios",
        ("academia", "crossfit", "pilates", "studio fitness", "treino funcional", "musculacao", "box de", "artes marciais", "jiu", "natacao"),
        ("gym", "fitness_center", "yoga_studio", "sports_club", "sports_activity_location"),
        ("apresentar os planos, horários e modalidades", "facilitar o contato de quem quer agendar uma aula experimental"),
        "planos, horários, modalidades, localização e canais de contato", 10,
    ),
    Segment(
        "saude", "Clínicas e saúde",
        ("clinica", "consultorio", "dentista", "odonto", "fisioterap", "psicolog", "nutricion", "medic", "laborator", "fonoaudiolog", "dermatolog", "oftalmo", "ortoped", "pediatr", "veterinar"),
        ("dentist", "dental_clinic", "doctor", "medical_clinic", "physiotherapist", "hospital", "medical_lab", "veterinary_care", "chiropractor", "skin_care_clinic"),
        ("apresentar as especialidades e a equipe", "facilitar o agendamento de consultas"),
        "especialidades, equipe, convênios, localização e agendamento", 15,
    ),
    Segment(
        "beleza", "Beleza e estética",
        ("salao", "salão", "beleza", "cabeleire", "barbearia", "manicure", "estetica", "sobrancelha", " spa ", "depila", "maquiagem", "unha", "cilios"),
        ("beauty_salon", "hair_salon", "barber_shop", "nail_salon", "spa", "hair_care", "beautician", "makeup_artist"),
        ("mostrar os serviços e trabalhos realizados", "facilitar os agendamentos"),
        "serviços, fotos de trabalhos, preços de referência e agendamento", 8,
    ),
    Segment(
        "alimentacao", "Restaurantes e alimentação",
        ("restaurante", "pizzaria", "hamburgueria", "lanchonete", " bar ", "cafeteria", "padaria", "doceria", "confeitaria", "sushi", "churrascaria", "acai", "sorveteria", "marmita", "food"),
        ("restaurant", "pizza_restaurant", "hamburger_restaurant", "cafe", "coffee_shop", "bakery", "bar", "meal_takeaway", "meal_delivery", "brazilian_restaurant", "japanese_restaurant", "ice_cream_shop", "confectionery"),
        ("mostrar o cardápio e os horários de funcionamento", "facilitar reservas e pedidos"),
        "cardápio, horários, localização, reservas e pedidos", 7,
    ),
    Segment(
        "automotivo", "Oficinas e serviços automotivos",
        ("oficina", "mecanic", "auto center", "autocenter", "funilaria", "lava jato", "lava-jato", "autoeletric", "auto eletric", "pneu", "borracharia", "estetica automotiva"),
        ("car_repair", "car_wash", "auto_parts_store", "tire_shop", "car_dealer"),
        ("apresentar os serviços e as especialidades da oficina", "facilitar pedidos de orçamento"),
        "serviços, especialidades, marcas atendidas, localização e pedido de orçamento", 10,
    ),
    Segment(
        "profissionais", "Serviços profissionais",
        ("advoca", "advogad", "contabil", "contador", "imobiliar", "arquitet", "engenhar", "consultoria", "despachante", "corretor", "seguro"),
        ("lawyer", "accounting", "real_estate_agency", "insurance_agency", "consultant", "architect"),
        ("transmitir credibilidade e apresentar as áreas de atuação", "facilitar o primeiro contato de novos clientes"),
        "áreas de atuação, equipe, diferenciais e formas de contato", 15,
    ),
    Segment(
        "educacao", "Escolas e cursos",
        ("escola", "curso", "idioma", "ingles", "autoescola", "auto escola", "reforco", "musica", "danca", "creche", "berçario", "bercario"),
        ("school", "primary_school", "secondary_school", "language_school", "driving_school", "preschool", "dance_school", "music_school"),
        ("apresentar os cursos, turmas e diferenciais", "facilitar o contato de quem quer se matricular"),
        "cursos, turmas, horários, estrutura e matrícula", 10,
    ),
    Segment(
        "pet", "Pet shops",
        ("pet shop", "petshop", "banho e tosa", " pet "),
        ("pet_store", "pet_care"),
        ("apresentar os serviços e produtos", "facilitar o agendamento de banho e tosa"),
        "serviços, produtos, horários e agendamento", 8,
    ),
    Segment(
        "varejo", "Lojas e comércio",
        ("loja", "boutique", "papelaria", "material de constru", "moveis", "móveis", "otica", "ótica", "floricultura", "presentes", "calcados", "roupas", "joalheria", "informatica"),
        ("store", "clothing_store", "furniture_store", "home_goods_store", "hardware_store", "jewelry_store", "shoe_store", "florist", "electronics_store", "book_store"),
        ("apresentar os produtos e novidades", "facilitar o contato e mostrar a localização"),
        "produtos, novidades, formas de pagamento, localização e contato", 7,
    ),
    Segment(
        "servicos", "Serviços em geral",
        ("eletricista", "encanador", "dedetiza", "limpeza", "marido de aluguel", "reforma", "pintor", "vidracaria", "serralheria", "marcenaria", "chaveiro", "grafica", "gráfica", "fotograf", "eventos", "buffet"),
        ("electrician", "plumber", "painter", "roofing_contractor", "general_contractor", "locksmith", "moving_company", "photographer", "event_planner", "laundry"),
        ("apresentar os serviços e trabalhos já realizados", "facilitar pedidos de orçamento"),
        "serviços, portfólio, área de atendimento e pedido de orçamento", 10,
    ),
)

DEFAULT_SEGMENT = Segment(
    "geral", "Outros negócios", (), (),
    ("apresentar melhor os serviços", "facilitar o contato com os clientes"),
    "serviços, diferenciais, localização e canais de contato", 5,
)

_BY_KEY = {s.key: s for s in SEGMENTS}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def get_segment(key: str | None) -> Segment:
    return _BY_KEY.get(key or "", DEFAULT_SEGMENT)


def detect_segment(*texts: str | None, google_types: list[str] | None = None) -> Segment:
    """Detecta o segmento pelo termo pesquisado, categoria do Google ou tipos do Places."""
    for t in google_types or []:
        for seg in SEGMENTS:
            if t in seg.google_types:
                return seg
    haystack = " " + " ".join(_norm(t) for t in texts if t) + " "
    for seg in SEGMENTS:
        if any(_norm(k) in haystack for k in seg.keywords):
            return seg
    return DEFAULT_SEGMENT


def all_segments() -> list[dict]:
    return [{"key": s.key, "label": s.label, "value": s.value} for s in (*SEGMENTS, DEFAULT_SEGMENT)]
