"""Convert the report's .docx to PDF with LibreOffice, updating the table of contents first
(a plain `soffice --convert-to pdf` leaves Word's TOC field empty).
Usage: python docx2pdf.py out/report.docx out/report.pdf"""
import os
import subprocess
import sys
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def main(src, dst):
    port = 2002 + os.getpid() % 1000
    proc = subprocess.Popen(["soffice", "--headless", "--invisible", "--nologo", "--norestore",
                             f"--accept=socket,host=127.0.0.1,port={port};urp;"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        for _ in range(60):
            try:
                ctx = resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise SystemExit("LibreOffice did not start")
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(str(Path(src).resolve())), "_blank", 0,
                                           (prop("Hidden", True),))
        idx = doc.getDocumentIndexes()
        for i in range(idx.getCount()):
            idx.getByIndex(i).update()
        doc.refresh()
        doc.storeToURL(uno.systemPathToFileUrl(str(Path(dst).resolve())), (prop("FilterName", "writer_pdf_Export"),))
        doc.close(True)
    finally:
        proc.terminate()
        proc.wait(timeout=30)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
