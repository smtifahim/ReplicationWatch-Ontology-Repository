"""Stages 1 and 2: registry record and text.
Stage 1 gives the article an ID, a content hash, a document type and the list of sections found.
Stage 2 turns the PDF into text. Docling is the production parser; this run uses pdftotext because Docling is not installed here,
and the parser version is recorded as such. Bibliographic fields come from the PDF itself (fallback); the Crossref lookup is not available here."""
import re, subprocess, json
from common import *


def pdftotext(pdf, first=None, last=None, layout=False):
    cmd = ["pdftotext", "-enc", "UTF-8"] + (["-layout"] if layout else [])
    if first: cmd += ["-f", str(first), "-l", str(last or first)]
    return subprocess.run(cmd + [str(pdf), "-"], capture_output=True, text=True, check=True).stdout


def pdfinfo(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    return dict(l.split(":", 1) for l in out.splitlines() if ":" in l)


SECTIONS = [  # (CDBO articleSectionType, regex that finds its heading in running text)
    ("Abstract", r"\bABSTRACT\b|\bAbstract\b"),
    ("Introduction", r"\b1\s+Introduction\b|\bINTRODUCTION\b"),
    ("Methods", r"\b2\s+Materials and Methods\b|\bMethods\b"),
    ("Results", r"\b4\s+Results\b|\bRESULTS\b"),
    ("Discussion", r"\b5\s+Discussion\b|\bDISCUSSION\b"),
    ("Conclusion", r"\b6\s+Conclusion|\bConclusions?\b"),
    ("References", r"\bReferences\b"),
    ("Tables", r"\bTABLE\s+\d|\bTable\s+\d"),
    ("Figures", r"\bFIGURE\s+\d|\bFigure\s+\d"),
]


def run(pdf):
    info = pdfinfo(pdf)
    pages = int(info["Pages"])
    page_text = [pdftotext(pdf, i) for i in range(1, pages + 1)]
    text = "\n".join(page_text)
    (OUT / "paper.txt").write_text(text, encoding="utf-8")
    chars_per_page = len(text) / pages
    secs = ["Title"] if info.get("Title", "").strip() else []
    secs += [n for n, rx in SECTIONS if re.search(rx, text)]
    low = text[:6000].lower()
    classification = "Secondary" if re.search(r"systematic review|meta-analysis|a review of", low) else "Primary"
    reg = {
        "Publication_ID": PUB_ID, "Reported_Study_ID": STUDY_ID,
        "Document_Type": "Native PDF" if chars_per_page > 500 else "Scanned PDF",
        "Full_Text_Available": "Yes", "Available_Sections": ", ".join(secs),
        "Article_Classification": classification, "Content_Hash": "sha256:" + sha256_file(pdf),
    }
    first = " ".join(page_text[0].split())
    title = info.get("Title", "").strip()
    doi = (re.search(r"https://doi\.org/(10\.\d{4,9}/[^\s]+)", first) or [None, None])[1]
    # authors: the text between the title and the first affiliation marker ("1 Center ...") on page 1
    m = re.search(re.escape(title.split(" (")[0]) + r".*?\)?\s+(?P<a>[A-Z][A-Za-z\.\s\-]+?\d(?:,\d)*(?:\s+[A-Z][A-Za-z\.\s\-]+?\d(?:,\d)*)*)\s+1\s+[A-Z]", first)
    authors = None
    if m:
        authors = re.sub(r"\d(?:,\d)*", "|", m.group("a")).strip(" |")
        authors = "; ".join(a.strip() for a in authors.split("|") if a.strip())
    ym = re.search(r"Developmental Science,?\s+(20\d\d)", first)
    subj = info.get("Subject", "")
    venue = re.match(r"([A-Za-z ]+?)\s+20\d\d", subj)
    bib = {
        "Publication_ID": PUB_ID, "Reported_Study_ID": STUDY_ID,
        "Article_Title": title or None, "Listed_Authors": authors,
        "Publication_Year": ym.group(1) if ym else None,
        "Publication_Venue": venue.group(1).strip() if venue else None,
        "DOI_Link": f"https://doi.org/{doi}" if doi else None,
        "Publication_Link": f"https://doi.org/{doi}" if doi else None,
    }
    parser = {"Parser_Version": f"pdftotext (poppler 24.02.0) used as fallback; Docling not installed in this run; bibliographic fields read from the PDF, no Crossref lookup"}
    log = dict(pdf=str(pdf.name), pages=pages, chars=len(text), chars_per_page=round(chars_per_page), md5=sha256_file(pdf)[:16], sections=secs,
               pdf_title=title, doi=doi)
    save_json("stage1_registry.json", dict(registry=reg, bibliographic=bib, parser=parser, log=log, page_chars=[len(p) for p in page_text]))
    return reg, bib, parser, page_text


if __name__ == "__main__":
    reg, bib, parser, _ = run(IN / "efd5369b-test.pdf")
    print(json.dumps(dict(reg=reg, bib=bib), indent=1))
