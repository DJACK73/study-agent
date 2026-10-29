from dataclasses import dataclass, field

SECTIONS = ("resume", "cartes", "schema", "tableau", "images", "sources")
TAILLES = {"normal": 11.0, "grand": 13.5}


@dataclass
class PdfOptions:
    modele: str = ""
    taille: str = "normal"
    sections: list[str] = field(default_factory=lambda: ["resume", "cartes"])

    @property
    def police_pt(self) -> float:
        return TAILLES[self.taille]

    @classmethod
    def from_dict(cls, d: dict) -> "PdfOptions":
        o = cls()
        o.modele = str(d.get("modele", ""))[:30]
        o.taille = d.get("taille") if d.get("taille") in TAILLES else "normal"
        s = [x for x in d.get("sections", o.sections) if x in SECTIONS]
        o.sections = s or o.sections
        return o
