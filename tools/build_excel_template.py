#!/usr/bin/env python3
"""Build the curation workbook (empty template) from the CDBO ontology and the layout file.

Usage: python build_excel_template.py cdbo-core-v0.3.ttl config/excel_layout.json out/cdbo_template.xlsx

Workbook design
  * One tab per major group listed in the layout file.
  * Row 1: a merged band naming each property group, row 2: the field keys (skos:altLabel).
    Both rows share one light colour per group. Definitions are in cell comments on row 2.
  * Top two rows and the identity columns are frozen. Cells wrap text by default.
  * Alternate rows are shaded light blue by a conditional-format rule, so the banding
    survives sorting and filtering.
  * Enumerated fields get dropdowns fed from the Lists tab.
"""
import datetime
import sys
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from cdbo_common import Cdbo
from cdbo_xlsx import FIRST_DATA_ROW, KEY_ROW, load_layout, plan
from build_data_dictionary import rows as dictionary_rows, COLS as DICT_COLS

THIN = Side(style="thin", color="A6A6A6")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
DECIMAL = "xsd:decimal"


def fill(hex_):
    return PatternFill(start_color=hex_, end_color=hex_, fill_type="solid")


def width_for(layout, key):
    w = layout.get("column_widths", {})
    return max(w.get(key, w.get("default", 22)), round(len(key) * 1.15) + 2)   # never narrower than the key


def add_readme(wb, o, layout, plans, stamp):
    ws = wb.active
    ws.title = "README"
    rows = [("CDBO curation workbook", ""),
            ("Ontology version", o.version),
            ("Layout", "config/excel_layout.json"),
            ("Generated (UTC)", stamp), ("", ""),
            ("How to use", ""),
            ("1", "Do not edit identity columns (grey bands). Sorting and filtering are safe because rows are matched by ID."),
            ("2", "Bold field keys are filled by the LLM. Italic grey keys are filled by scripts, lookups or the SciScore API. Edit any cell when correcting."),
            ("3", "Use the literal text 'Not Specified' when the article does not report a value. Do not leave LLM-extracted cells empty (Claim_Source_Reference may be empty)."),
            ("4", "Dropdown columns accept only the listed values. Hover over a field key to read its definition."),
            ("5", "Do not retype evidence quotes. They must stay verbatim."), ("", ""),
            ("Group colours", "")]
    for r, (a, b) in enumerate(rows, 1):
        ws.cell(r, 1, a); ws.cell(r, 2, b)
    ws["A1"].font = Font(bold=True, size=14)
    for r in (6, 13):
        ws.cell(r, 1).font = Font(bold=True)
    r = len(rows) + 1
    for g, c in layout["group_colors"].items():
        ws.cell(r, 1, g).fill = fill(c)
        ws.cell(r, 2, "")
        r += 1
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 110
    for row in ws.iter_rows():
        for c in row:
            c.alignment = WRAP_TOP


def add_lists(wb, o):
    ws = wb.create_sheet("Lists")
    refs = {}
    for ci, (name, vals) in enumerate(sorted(o.enums.items()), 1):
        ws.cell(1, ci, name).font = Font(bold=True)
        for ri, v in enumerate(vals, 2):
            ws.cell(ri, ci, v)
        L = get_column_letter(ci)
        refs[name] = f"=Lists!${L}$2:${L}${len(vals) + 1}"
        ws.column_dimensions[L].width = 24
    return refs


def add_tab(wb, o, layout, p, refs):
    ws = wb.create_sheet(p.name)
    last = FIRST_DATA_ROW - 1 + int(layout.get("max_rows", 2000))
    band = layout["banding_color"]
    colors = layout["group_colors"]
    col = 1
    for gkey, glabel, gcols in p.spans:
        c0 = col
        for c in gcols:
            cell1 = ws.cell(1, col)
            cell2 = ws.cell(KEY_ROW, col, c.key)
            hx = colors.get(gkey, "EEEEEE")
            for cell in (cell1, cell2):
                cell.fill = fill(hx); cell.border = BOX
            cell2.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
            llm = c.field.role == "extracted"
            cell2.font = Font(bold=True) if (llm or c.identity) else Font(italic=True, color="595959")
            f = c.field
            tip = [f.label, "", f.description]
            if f.examples:
                tip += ["", "Example: " + " | ".join(f.examples)]
            if f.range_kind == "enum":
                tip += ["", "Allowed: " + "; ".join(o.enums[f.range_name])]
            tip += ["", "Filled by: " + ("identity (registry)" if c.identity else
                    "LLM" if llm else {"preprocessing": "registry script", "mapping": "grounding/registration script",
                                       "lookupOnly": "lookup / API / pipeline"}.get(f.role, f.role))]
            cm = Comment("\n".join(tip), "CDBO")
            cm.width, cm.height = 380, 260
            cell2.comment = cm
            ws.column_dimensions[get_column_letter(col)].width = width_for(layout, c.key)
            # column-level defaults so new rows wrap and stay text
            cd = ws.column_dimensions[get_column_letter(col)]
            cd.alignment = WRAP_TOP
            if not (f.range_kind == "datatype" and f.range_name == DECIMAL):
                cd.number_format = "@"
            if f.range_kind == "enum" and not c.identity:
                dv = DataValidation(type="list", formula1=refs[f.range_name], allow_blank=True,
                                    showErrorMessage=True, errorTitle="Value not allowed",
                                    error="Pick a value from the list.")
                ws.add_data_validation(dv)
                L = get_column_letter(col)
                dv.add(f"{L}{FIRST_DATA_ROW}:{L}{last}")
            col += 1
        ws.cell(1, c0, glabel).font = Font(bold=True)
        ws.cell(1, c0).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if col - 1 > c0:
            ws.merge_cells(start_row=1, start_column=c0, end_row=1, end_column=col - 1)
    n = len(p.columns)
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[KEY_ROW].height = 34
    ws.freeze_panes = ws.cell(FIRST_DATA_ROW, p.n_identity + 1)
    ws.conditional_formatting.add(
        f"A{FIRST_DATA_ROW}:{get_column_letter(n)}{last}",
        FormulaRule(formula=["MOD(ROW(),2)=0"], fill=fill(band)))
    ws.auto_filter.ref = f"A{KEY_ROW}:{get_column_letter(n)}{KEY_ROW}"
    return ws


def add_dictionary(wb, o):
    ws = wb.create_sheet("Data_Dictionary")
    ws.append(DICT_COLS)
    for r in dictionary_rows(o):
        ws.append([r[c] for c in DICT_COLS])
    for c in ws[1]:
        c.font = Font(bold=True); c.fill = fill("D9D9D9")
    for i, cname in enumerate(DICT_COLS, 1):
        ws.column_dimensions[get_column_letter(i)].width = 60 if cname in ("Definition", "Standards_And_Sources") else 24
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = WRAP_TOP
    ws.freeze_panes = "B2"


def build(ttl, layout_path, out):
    o = Cdbo(ttl)
    layout = load_layout(layout_path)
    plans, warns = plan(o, layout)
    wb = Workbook()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    add_readme(wb, o, layout, plans, stamp)
    refs = add_lists(wb, o)
    for p in plans:
        add_tab(wb, o, layout, p, refs)
    add_dictionary(wb, o)
    # tab order: README, data tabs, Lists, Data_Dictionary
    order = ["README"] + [p.name for p in plans] + ["Lists", "Data_Dictionary"]
    wb._sheets = [wb[n] for n in order]
    wb.save(out)
    for w in warns:
        print("WARN", w)
    print(f"wrote {out}: " + ", ".join(f"{p.name} ({len(p.columns)} cols)" for p in plans))
    return 0


if __name__ == "__main__":
    sys.exit(build(sys.argv[1], sys.argv[2], sys.argv[3]))
