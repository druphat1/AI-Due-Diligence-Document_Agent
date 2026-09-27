"""The due-diligence check catalog.

Each check is a retrieval query + extraction instructions + a severity
rubric. Eight checks — enough to demonstrate the discipline without
pretending to be full M&A diligence.
"""

from pydantic import BaseModel


class CheckSpec(BaseModel):
    id: str
    name: str
    category: str
    query: str            # retrieval query against the index
    instructions: str     # what the extractor should look for
    severity_hint: str    # how to grade what it finds


CHECKS: list[CheckSpec] = [
    CheckSpec(
        id="change_of_control",
        name="Change of Control",
        category="Commercial",
        query="change of control merger acquisition sale of assets ownership transfer consent",
        instructions=(
            "Look for clauses triggered by a change of control, merger, "
            "acquisition, or sale of substantially all assets: consent "
            "requirements, termination rights, or events of default."
        ),
        severity_hint=(
            "HIGH if a counterparty can terminate or must consent to a change "
            "of control; MEDIUM if notice-only; LOW/NO_ISSUE if silent."
        ),
    ),
    CheckSpec(
        id="assignment_restrictions",
        name="Assignment Restrictions",
        category="Commercial",
        query="assignment assign transfer without prior written consent",
        instructions=(
            "Look for restrictions on assigning or transferring the agreement: "
            "consent requirements, outright prohibitions, or free assignability "
            "to affiliates/successors."
        ),
        severity_hint=(
            "HIGH if assignment is prohibited or requires counterparty consent "
            "(blocks asset deals); MEDIUM if consent not to be unreasonably "
            "withheld; LOW if freely assignable to affiliates."
        ),
    ),
    CheckSpec(
        id="termination_rights",
        name="Termination Rights",
        category="Commercial",
        query="termination terminate convenience breach notice period expiry term renewal",
        instructions=(
            "Look for termination rights: termination for convenience, "
            "termination for breach, notice periods, auto-renewal, and expiry."
        ),
        severity_hint=(
            "HIGH if a key counterparty can terminate for convenience on short "
            "notice; MEDIUM for convenience with long notice or cure periods; "
            "LOW for breach-only termination."
        ),
    ),
    CheckSpec(
        id="exclusivity",
        name="Exclusivity",
        category="Commercial",
        query="exclusive exclusivity sole provider non-compete most favored",
        instructions=(
            "Look for exclusivity or non-compete obligations binding the "
            "company: exclusive dealing, sole-provider clauses, most-favored-"
            "customer terms."
        ),
        severity_hint=(
            "HIGH if the company is locked into exclusivity that constrains the "
            "business post-close; MEDIUM for narrow/limited exclusivity."
        ),
    ),
    CheckSpec(
        id="ip_ownership",
        name="IP Ownership & Licensing",
        category="IP",
        query="intellectual property ownership license work product invention assignment copyright patent",
        instructions=(
            "Look for who owns IP: work-product/invention assignment to the "
            "company vs. IP merely licensed in, retained by a licensor, or "
            "carve-outs for pre-existing IP."
        ),
        severity_hint=(
            "HIGH if core IP is owned by a third party or not assigned; MEDIUM "
            "for license-only dependencies or carve-outs; NO_ISSUE for clean "
            "assignment to the company."
        ),
    ),
    CheckSpec(
        id="material_liabilities",
        name="Material Liabilities & Indemnities",
        category="Liability",
        query="liability indemnify indemnification damages unlimited cap limitation losses",
        instructions=(
            "Look for liability exposure: indemnification obligations, "
            "unlimited/uncapped liability, liability caps, consequential "
            "damages waivers."
        ),
        severity_hint=(
            "HIGH for uncapped indemnities or unlimited liability owed by the "
            "company; MEDIUM for caps above contract value; LOW for standard "
            "caps and mutual waivers."
        ),
    ),
    CheckSpec(
        id="debt_guarantees",
        name="Debt & Guarantees",
        category="Debt",
        query="loan facility debt borrow guarantee guarantor security interest covenant default",
        instructions=(
            "Look for debt terms: facilities, guarantees, security interests, "
            "financial covenants, events of default, acceleration rights."
        ),
        severity_hint=(
            "HIGH for guarantees, security over assets, or defaults triggered "
            "by a transaction; MEDIUM for ordinary debt with standard covenants."
        ),
    ),
    CheckSpec(
        id="litigation_regulatory",
        name="Litigation & Regulatory",
        category="Legal",
        query="litigation lawsuit claim proceeding arbitration regulatory investigation fine penalty court",
        instructions=(
            "Look for pending or threatened litigation, arbitration, "
            "regulatory investigations, fines, or compliance issues."
        ),
        severity_hint=(
            "HIGH for active litigation or regulatory investigations; MEDIUM "
            "for threatened claims; LOW/NO_ISSUE for standard reps that none exist."
        ),
    ),
]

CHECKS_BY_ID = {c.id: c for c in CHECKS}
