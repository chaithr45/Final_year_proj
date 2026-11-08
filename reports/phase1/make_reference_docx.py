"""Style the Word template used by build.sh (reports/phase1/reference.docx): Times New Roman 12 pt, 1.5 line
spacing, justified body text, each chapter on a new page, compact 10 pt tables, 1-inch margins."""
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

here = Path(__file__).resolve().parent
ref = here / "reference.docx"
ref.write_bytes(subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"], capture_output=True,
                               check=True).stdout)
doc = Document(str(ref))
for sec in doc.sections:
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(1)
STY = {s.name: s for s in doc.styles}
INK = RGBColor(0x0B, 0x0B, 0x0B)


def font(s, size=None, bold=None, color=INK, name="Times New Roman"):
    s.font.name = name
    rpr = s.element.get_or_add_rPr()
    rfonts = rpr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts")
    if rfonts is not None:
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        for a in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
            rfonts.attrib.pop(W + a, None)
        for a in ("ascii", "hAnsi", "cs", "eastAsia"):
            rfonts.set(W + a, name)
    if size:
        s.font.size = Pt(size)
    if bold is not None:
        s.font.bold = bold
    if color is not None:
        s.font.color.rgb = color


for name in ("Normal", "Body Text", "First Paragraph"):
    if name in STY:
        s = STY[name]
        font(s, 12)
        s.paragraph_format.line_spacing = 1.5
        s.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        s.paragraph_format.space_after = Pt(6)
for name, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 12)):
    s = STY[name]
    font(s, size, bold=True)
    s.paragraph_format.space_before = Pt(18 if name == "Heading 1" else 12)
    s.paragraph_format.space_after = Pt(6)
    s.paragraph_format.keep_with_next = True
STY["Heading 1"].paragraph_format.page_break_before = True
for name, size in (("Title", 20), ("Subtitle", 14), ("Author", 12), ("Date", 12)):
    if name in STY:
        font(STY[name], size, bold=(name == "Title"))
        STY[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
for name in ("Compact",):
    if name in STY:
        font(STY[name], 10)
        STY[name].paragraph_format.line_spacing = 1.0
        STY[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
for name in ("Image Caption", "Table Caption", "Caption"):
    if name in STY:
        font(STY[name], 10)
        STY[name].font.italic = True
        STY[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
for name in ("Block Text",):
    if name in STY:
        font(STY[name], 12)
        STY[name].font.italic = True
for name in ("Bibliography",):
    if name in STY:
        font(STY[name], 10)
        STY[name].paragraph_format.line_spacing = 1.15
        STY[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
doc.save(str(ref))
print("styled", ref)
