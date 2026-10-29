"""Perfis de segmento: como um site pode ajudar cada tipo de negócio (em português e inglês).

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
    site_items: str
    value: int  # 0..15, padrão; pode ser sobrescrito na configuração da pontuação
    label_en: str = "Other businesses"
    benefits_en: tuple[str, str] = ("present your services better", "make it easier for customers to reach you")
    site_items_en: str = "services, what sets you apart, location and contact options"

    def text(self, lang: str) -> tuple[str, tuple[str, str], str]:
        if lang == "en":
            return self.label_en, self.benefits_en, self.site_items_en
        return self.label, self.benefits, self.site_items


SEGMENTS: tuple[Segment, ...] = (
    Segment(
        "academia", "Academias e estúdios",
        ("academia", "crossfit", "pilates", "studio fitness", "treino funcional", "musculacao", "box de", "artes marciais", "jiu", "natacao",
         "gym", "fitness", "yoga", "martial arts", "boxing", "personal train", "kickboxing", "barre", "swim"),
        ("gym", "fitness_center", "yoga_studio", "sports_club", "sports_activity_location"),
        ("apresentar os planos, horários e modalidades", "facilitar o contato de quem quer agendar uma aula experimental"),
        "planos, horários, modalidades, localização e canais de contato", 10,
        "Gyms and studios",
        ("show your memberships, class schedule and programs", "make it easy for people to book a free trial class"),
        "memberships, class schedule, programs, location and contact options",
    ),
    Segment(
        "saude", "Clínicas e saúde",
        ("clinica", "consultorio", "dentista", "odonto", "fisioterap", "psicolog", "nutricion", "medic", "laborator", "fonoaudiolog", "dermatolog", "oftalmo", "ortoped", "pediatr", "veterinar",
         "dentist", "dental", "clinic", "chiropract", "physical therap", "med spa", "doctor", "orthodont", "optometr", "therapist", "urgent care",
         "quiropraxia", "psycholog", "nutritionist", "dietitian", "fono"),
        ("dentist", "dental_clinic", "doctor", "medical_clinic", "physiotherapist", "hospital", "medical_lab", "veterinary_care", "chiropractor", "skin_care_clinic"),
        ("apresentar as especialidades e a equipe", "facilitar o agendamento de consultas"),
        "especialidades, equipe, convênios, localização e agendamento", 15,
        "Clinics and healthcare",
        ("present your services and your team", "make it easier for patients to book appointments"),
        "services, team, insurance accepted, location and appointment booking",
    ),
    Segment(
        "automotivo", "Oficinas e serviços automotivos",
        ("oficina", "mecanic", "auto center", "autocenter", "funilaria", "lava jato", "lava-jato", "autoeletric", "auto eletric", "pneu", "borracharia", "estetica automotiva",
         "auto repair", "mechanic", "body shop", "collision", "tire", "car wash", "detailing", "transmission", "oil change", "towing",
         "guincho", "auto electr"),
        ("car_repair", "car_wash", "auto_parts_store", "tire_shop", "car_dealer"),
        ("apresentar os serviços e as especialidades da oficina", "facilitar pedidos de orçamento"),
        "serviços, especialidades, marcas atendidas, localização e pedido de orçamento", 10,
        "Auto services",
        ("present your services and specialties", "make it easy to request a quote"),
        "services, specialties, makes you work on, location and quote requests",
    ),
    Segment(
        "beleza", "Beleza e estética",
        ("salao", "salão", "beleza", "cabeleire", "barbearia", "manicure", "estetica", "sobrancelha", " spa ", "depila", "maquiagem", "unha", "cilios",
         "salon", "barber", "nail", "lash", "brow", "beauty", "hair", "waxing", "tattoo", "tatua", " spas ", "day spa", "maquia", "makeup"),
        ("beauty_salon", "hair_salon", "barber_shop", "nail_salon", "spa", "hair_care", "beautician", "makeup_artist"),
        ("mostrar os serviços e trabalhos realizados", "facilitar os agendamentos"),
        "serviços, fotos de trabalhos, preços de referência e agendamento", 8,
        "Beauty and personal care",
        ("show your services and past work", "make booking easier"),
        "services, photos of your work, pricing and online booking",
    ),
    Segment(
        "alimentacao", "Restaurantes e alimentação",
        ("restaurante", "pizzaria", "hamburgueria", "lanchonete", " bar ", "cafeteria", "padaria", "doceria", "confeitaria", "sushi", "churrascaria", "acai", "sorveteria", "marmita", "food",
         "restaurant", "pizza", "burger", "cafe", "coffee", "baker", "taco", "bbq", "diner", "catering", " deli", "brewery",
         "cake", "ice cream", "sandwich", " bars ", " bares ", "meal prep", "buffet"),
        ("restaurant", "pizza_restaurant", "hamburger_restaurant", "cafe", "coffee_shop", "bakery", "bar", "meal_takeaway", "meal_delivery", "brazilian_restaurant", "japanese_restaurant", "ice_cream_shop", "confectionery", "mexican_restaurant", "american_restaurant"),
        ("mostrar o cardápio e os horários de funcionamento", "facilitar reservas e pedidos"),
        "cardápio, horários, localização, reservas e pedidos", 7,
        "Restaurants and food",
        ("show your menu and opening hours", "make reservations and orders easier"),
        "menu, hours, location, reservations and online ordering",
    ),
    Segment(
        "profissionais", "Serviços profissionais",
        ("advoca", "advogad", "contabil", "contador", "imobiliar", "arquitet", "engenhar", "consultoria", "despachante", "corretor", "seguro",
         "law firm", "attorney", "lawyer", "accountant", "accounting", "cpa", "bookkeep", "tax prep", "real estate", "realtor", "insurance", "consulting", "architect", "engineering"),
        ("lawyer", "accounting", "real_estate_agency", "insurance_agency", "consultant", "architect"),
        ("transmitir credibilidade e apresentar as áreas de atuação", "facilitar o primeiro contato de novos clientes"),
        "áreas de atuação, equipe, diferenciais e formas de contato", 15,
        "Professional services",
        ("build credibility and present your practice areas", "make it easier for new clients to get in touch"),
        "practice areas, team, credentials and contact options",
    ),
    Segment(
        "educacao", "Escolas e cursos",
        ("escola", "curso", "idioma", "ingles", "autoescola", "auto escola", "reforco", "musica", " danca", "creche", "berçario", "bercario",
         "school", "tutoring", "daycare", "preschool", "academy", "lessons", "learning center", " dance"),
        ("school", "primary_school", "secondary_school", "language_school", "driving_school", "preschool", "dance_school", "music_school", "child_care_agency"),
        ("apresentar os cursos, turmas e diferenciais", "facilitar o contato de quem quer se matricular"),
        "cursos, turmas, horários, estrutura e matrícula", 10,
        "Schools and courses",
        ("present your programs and what sets you apart", "make it easy for families to enroll"),
        "programs, schedules, facilities and enrollment",
    ),
    Segment(
        "pet", "Pet shops",
        ("pet shop", "petshop", "banho e tosa", " pet ", "pet groom", "dog groom", "kennel", "dog train", "pet store", "dog boarding", "para caes", "adestra"),
        ("pet_store", "pet_care"),
        ("apresentar os serviços e produtos", "facilitar o agendamento de banho e tosa"),
        "serviços, produtos, horários e agendamento", 8,
        "Pet services",
        ("present your services and products", "make grooming appointments easier to book"),
        "services, products, hours and booking",
    ),
    Segment(
        "varejo", "Lojas e comércio",
        ("loja", "boutique", "papelaria", "material de constru", "materiais de constru", "moveis", "móveis", "otica", "ótica", "floricultura", "presentes", "calcados", "roupas", "joalheria", "informatica",
         "store", "florist", "furniture", "jewelry", "gift shop", "clothing", "hardware"),
        ("store", "clothing_store", "furniture_store", "home_goods_store", "hardware_store", "jewelry_store", "shoe_store", "florist", "electronics_store", "book_store"),
        ("apresentar os produtos e novidades", "facilitar o contato e mostrar a localização"),
        "produtos, novidades, formas de pagamento, localização e contato", 7,
        "Retail stores",
        ("showcase your products and new arrivals", "help people find and contact your store"),
        "products, new arrivals, payment options, location and contact",
    ),
    Segment(
        "servicos", "Serviços em geral",
        ("eletricista", "encanador", "dedetiza", "limpeza", "marido de aluguel", "reforma", "pintor", "vidracaria", "serralheria", "marcenaria", "chaveiro", "grafica", "gráfica", "fotograf", "eventos",
         "ar condicionado", "ar-condicionado", "telhad", "calha", "paisagis", "jardin", "piscina", "mudanca", "frete", "celular", "lavanderia",
         "plumb", "electrician", "hvac", "roofing", "roofer", "landscap", "lawn", "cleaning", "maid", "handyman", "painting", "painter", "contractor", "remodel",
         "pest control", "locksmith", "moving", "photograph", "pressure wash", "pool", "fencing", "flooring", "garage door", "junk removal", "tree service",
         "glass", "cabinet", "mover", "event plann", "print shop", "phone repair", "dry clean", "laundr"),
        ("electrician", "plumber", "painter", "roofing_contractor", "general_contractor", "locksmith", "moving_company", "photographer", "event_planner", "laundry"),
        ("apresentar os serviços e trabalhos já realizados", "facilitar pedidos de orçamento"),
        "serviços, portfólio, área de atendimento e pedido de orçamento", 10,
        "Home and local services",
        ("show your services and past projects", "make it easy to request a quote"),
        "services, project gallery, service area and quote requests",
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


STRONG_PHRASES = (
    ("health food", "varejo"), ("vitamin", "varejo"), ("supplement", "varejo"), ("suplemento", "varejo"),
    ("produtos naturais", "varejo"), ("grocery", "varejo"), ("pet store", "pet"), ("pet shop", "pet"),
)


def get_segment(key: str | None) -> Segment:
    return _BY_KEY.get(key or "", DEFAULT_SEGMENT)


def detect_segment(*texts: str | None, google_types: list[str] | None = None, preferred: str | None = None) -> Segment:
    """Detecta o segmento: 1) tipos do Places; 2) segmento escolhido no seletor; 3) palavras-chave."""
    for t in google_types or []:
        for seg in SEGMENTS:
            if t in seg.google_types:
                return seg
    if preferred in _BY_KEY:
        return _BY_KEY[preferred]
    haystack = " " + " ".join(_norm(t) for t in texts if t) + " "
    # Expressões que valem mais que palavras soltas ("health food store" é loja, não restaurante)
    for phrase, key in STRONG_PHRASES:
        if phrase in haystack:
            return _BY_KEY[key]
    for seg in SEGMENTS:
        if any(_norm(k) in haystack for k in seg.keywords):
            return seg
    return DEFAULT_SEGMENT


def all_segments() -> list[dict]:
    return [{"key": s.key, "label": s.label, "value": s.value} for s in (*SEGMENTS, DEFAULT_SEGMENT)]
