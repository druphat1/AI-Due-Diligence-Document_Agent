"""Generate a synthetic data room covering all 8 DD checks.

Each document places known clauses on known pages (see DOCS / EXPECTED)
so extraction results are verifiable by inspection and in tests.

Usage: python -m scripts.make_sample_docs
"""

from pathlib import Path

import pymupdf

FILLER = (
    "The party agrees to the terms set forth herein. This section governs "
    "the general obligations of the parties during the term of the agreement. "
)

# filename -> {page: clause}
DOCS: dict[str, dict[int, str]] = {
    "Company_Overview.pdf": {
        2: "LEGAL PROCEEDINGS. The Company is currently a defendant in a "
           "contract dispute filed in the Delaware Court of Chancery and is "
           "the subject of an ongoing regulatory investigation by the SEC "
           "regarding its revenue recognition practices."
    },
    "Customer_Contract_01.pdf": {
        2: "CHANGE OF CONTROL. In the event of a Change of Control of either "
           "party, including any merger, acquisition, or sale of substantially "
           "all assets, any assignment of this Agreement in connection with a "
           "Change of Control requires the prior written consent of the other "
           "party.",
        3: "EXCLUSIVITY. During the term of this Agreement, the Company shall "
           "sell its products exclusively through the Customer and shall not "
           "offer the products to any other distributor in the Territory.",
        4: "TERMINATION. The Customer may terminate this Agreement for "
           "convenience upon thirty (30) days prior written notice to the "
           "Company.",
    },
    "Customer_Contract_02.pdf": {
        2: "ASSIGNMENT. Neither party may assign or transfer this Agreement, "
           "in whole or in part, without the prior written consent of the "
           "other party, and any purported assignment in violation of this "
           "section shall be void.",
        3: "INDEMNIFICATION. The Supplier shall indemnify, defend, and hold "
           "harmless the Customer from and against all losses, damages, and "
           "liabilities arising out of the Services, without any limitation "
           "or cap on liability.",
    },
    "Employment_Agreement.pdf": {
        2: "INTELLECTUAL PROPERTY. The Employee hereby assigns to the Company "
           "all right, title, and interest in any inventions, work product, "
           "and developments made within the scope of employment, except "
           "inventions listed on Exhibit A as pre-existing IP of the Employee.",
    },
    "Loan_Agreement.pdf": {
        2: "GUARANTEE. The obligations of the Borrower under this Facility "
           "Agreement are unconditionally and irrevocably guaranteed by the "
           "Parent, and the Borrower has granted a first-ranking security "
           "interest over substantially all of its assets.",
        3: "EVENTS OF DEFAULT. A Change of Control of the Borrower shall "
           "constitute an immediate Event of Default under this Facility "
           "Agreement, entitling the Lender to accelerate all outstanding "
           "amounts.",
    },
    "IP_Agreement.pdf": {
        2: "LICENSE. The Licensor grants the Company a non-exclusive, "
           "non-transferable license to use the Platform IP. The Licensor "
           "retains all right, title, and ownership of the Platform IP, and "
           "no ownership interest is transferred to the Company.",
    },
}

# check_id -> (document_id, page) where the decisive clause lives
EXPECTED = {
    "change_of_control": [("customer_contract_01", 2), ("loan_agreement", 3)],
    "assignment_restrictions": [("customer_contract_02", 2)],
    "termination_rights": [("customer_contract_01", 4)],
    "exclusivity": [("customer_contract_01", 3)],
    "ip_ownership": [("ip_agreement", 2), ("employment_agreement", 2)],
    "material_liabilities": [("customer_contract_02", 3)],
    "debt_guarantees": [("loan_agreement", 2)],
    "litigation_regulatory": [("company_overview", 2)],
}


def make_pdf(path: Path, num_pages: int, clauses: dict[int, str]) -> None:
    doc = pymupdf.open()
    for i in range(1, num_pages + 1):
        page = doc.new_page()
        body = FILLER * 12
        if i in clauses:
            body += "\n\n" + clauses[i]
        page.insert_textbox(pymupdf.Rect(72, 72, 540, 740), body)
    doc.save(path)
    doc.close()


def main(out_dir: str = "data/test") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, clauses in DOCS.items():
        make_pdf(out / name, num_pages=5, clauses=clauses)
        print(f"wrote {out / name} (clauses on pages {sorted(clauses)})")


if __name__ == "__main__":
    main()
