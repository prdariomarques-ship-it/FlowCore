"""Investor classification — investidor geral / qualificado / profissional.

Legal basis: CVM Resolução nº 30, de 11/05/2021 (em vigor desde 01/06/2021),
que revogou a Instrução CVM 539/2013 e passou a reger, entre outras
matérias, as categorias de investidor:
  - art. 11: investidor profissional
  - art. 12: investidor qualificado
Alterada por Resolução CVM 162/2022 (incluiu "fundos patrimoniais" no
art. 11 e revisou, por consulta, o rol de certificações reconhecidas no
art. 12, III) e Resolução CVM 179/2023 (renomeou "agente autônomo de
investimento" para "assessor de investimento" em todo o texto).

Duas trilhas de enquadramento (independentes uma da outra):
  - Patrimônio declarado + termo de adesão por escrito:
      > R$ 10.000.000,00  -> investidor profissional (art. 11, termo
        conforme Anexo A)
      > R$ 1.000.000,00   -> investidor qualificado (art. 12, II, termo
        conforme Anexo B)
  - Certificação técnica (art. 12, III): pessoa física aprovada em exame
    ou certificação que a CVM aceite como pré-requisito para registro de
    assessor de investimento, administrador de carteira, analista ou
    consultor de valores mobiliários -> investidor qualificado quanto a
    recursos próprios, independente de patrimônio.

IMPORTANTE — isto é dado regulatório, não uma constante para confiar
indefinidamente. A Agenda Regulatória 2026 da CVM (Deliberação D3468,
Reunião de Regulação nº 27, 03/12/2025) já lista "revisão do conceito de
investidor qualificado" como pauta prevista para 2026, e o rol de
certificações do art. 12, III já foi ampliado uma vez por consulta (2022)
sem gerar uma nova numeração de resolução. Antes de confiar nisto para
uma decisão real de compliance, reconfirme os valores abaixo contra o
texto consolidado em
https://conteudo.cvm.gov.br/legislacao/resolucoes/resol030.html
"""
from __future__ import annotations

LEGAL_BASIS = (
    "CVM Resolução nº 30/2021, arts. 11 e 12 "
    "(conforme alterada pelas Resoluções CVM 162/2022 e 179/2023)"
)

PROFESSIONAL_INVESTOR_THRESHOLD = 10_000_000.00
QUALIFIED_INVESTOR_THRESHOLD = 1_000_000.00

# Certificações que a CVM reconhece hoje como pré-requisito de registro de
# assessor de investimento, administrador de carteira, analista ou
# consultor de valores mobiliários e que, portanto, sob o art. 12, III,
# bastam por si só (sem exigência de patrimônio) para a condição de
# investidor qualificado quanto a recursos próprios. Rol ampliado por
# consulta da CVM em 2022 (B3 Comunicado Externo CE 001-2022) além dos
# exames mais comumente citados (CGA, CEA, CFP, CNPI).
ACCEPTED_CERTIFICATIONS: tuple[str, ...] = (
    "CGA", "CEA", "CFP", "CNPI", "CFA", "ACIIA", "PQO", "CPA-10", "CPA-20",
    "CAIA", "FRM", "CQF", "CFG", "CGE", "CA-600", "CA-400", "CA-300",
    "CTP", "FPA",
)

CATEGORIES: tuple[str, ...] = ("geral", "qualificado", "profissional")

CATEGORY_LABELS: dict[str, str] = {
    "geral": "Investidor geral",
    "qualificado": "Investidor qualificado",
    "profissional": "Investidor profissional",
}


def suggest_investor_category(declared_investments: float | None, certification: str | None) -> str:
    """Classificação pura a partir do patrimônio declarado e/ou
    certificação informados — não decide sozinha: quem persiste essa
    categoria em um cliente real (storage.client_repo.ClientRepository.
    set_investor_classification) também registra o momento do termo de
    adesão por escrito exigido pelos Anexos A/B da Resolução CVM 30."""
    if declared_investments is not None and declared_investments >= PROFESSIONAL_INVESTOR_THRESHOLD:
        return "profissional"
    if certification and certification.strip().upper() in ACCEPTED_CERTIFICATIONS:
        return "qualificado"
    if declared_investments is not None and declared_investments >= QUALIFIED_INVESTOR_THRESHOLD:
        return "qualificado"
    return "geral"
