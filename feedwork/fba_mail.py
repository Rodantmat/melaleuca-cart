#!/usr/bin/env python3
"""
fba_mail.py - the two e-mails that follow a shipment.   Settings (credentials.txt, same folder as sd_tools.py):
    MAIL_MODE=off|eml|send        off (default) = nothing, eml = write .eml files next to the PDFs for you to look at, send = really send
    GMAIL_USER=rodolfoaamattos@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx        (a Google "app password", not the normal one)
    JESSICA_EMAIL=jessicamejia.h@hotmail.com       UPS_DOCS_EMAIL=internationaldocs.us@ups.com   UPS_DOCS_CC=cusmaprocessing@ups.com
"""
import datetime, mimetypes, os, smtplib, ssl
from email.message import EmailMessage
import sd_tools as S
import fba_docs as D


def settings():
    c = {}
    try: c = S._credentials()
    except Exception: pass
    return {"mode": (c.get("MAIL_MODE") or "off").lower(), "user": c.get("GMAIL_USER") or "rodolfoaamattos@gmail.com", "pw": c.get("GMAIL_APP_PASSWORD", ""),
            "jessica": c.get("JESSICA_EMAIL") or "jessicamejia.h@hotmail.com", "ups": c.get("UPS_DOCS_EMAIL") or "internationaldocs.us@ups.com",
            "ups_cc": c.get("UPS_DOCS_CC") or "cusmaprocessing@ups.com"}


def build(sender, to, subject, body, files, cc=None):
    m = EmailMessage(); m["From"] = sender; m["To"] = to; m["Subject"] = subject
    if cc: m["Cc"] = cc
    m.set_content(body)
    for f in files:
        ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
        m.add_attachment(open(f, "rb").read(), maintype=ctype.split("/")[0], subtype=ctype.split("/")[1], filename=os.path.basename(f))
    return m


def messages(st, files, today, cfg):
    """[(label, EmailMessage)]"""
    month = D.previous_month_tag(today)               # always one month behind
    y, mo = month.split("-"); o = st["origin"].strip().title()
    tracking = [t for l in st["legs"] for t in l["tracking"]]
    fba = [l.get("fbaId") for l in st["legs"]]
    jess = build(cfg["user"], cfg["jessica"], "envio %s %s-%s" % (o, mo, y), "",
                 [files[k] for k in ("fba", "cusma", "inv", "ups", "fda")])
    body = ("Hello,\n\nPlease find attached the CUSMA certificate of origin and the commercial invoice for the following %s shipment "
            "(Flipping Magic LLC, UPS account via Shippo) going to Amazon %s.\n\nTracking numbers:\n%s\n\nAmazon shipment ID(s): %s\n\n"
            "Please apply the USMCA/CUSMA preference at import.\n\nThank you,\nRodolfo Antunes\nFlipping Magic LLC\nflippingmagic.sales@gmail.com\n") % (
        o, ", ".join(l["warehouse"] for l in st["legs"]), "\n".join("  " + t for t in tracking), ", ".join(x for x in fba if x))
    ups = build(cfg["user"], cfg["ups"], "CUSMA and commercial invoice - %s %s-%s - %s" % (o, mo, y, ", ".join(tracking[:3]) + (" ..." if len(tracking) > 3 else "")),
                body, [files["cusma"], files["inv"]], cc=cfg["ups_cc"])
    return [("Jessica", jess), ("UPS documents", ups)]


def send_all(st, files, today=None, mode=None, say=print):
    cfg = settings(); mode = (mode or cfg["mode"]); today = today or datetime.date.today()
    msgs = messages(st, files, today, cfg)
    if mode == "off": return "mail is OFF (MAIL_MODE=off) - nothing sent. Set MAIL_MODE=send in credentials.txt to go live."
    done = []
    if mode == "eml":
        for label, m in msgs:
            p = os.path.join(os.path.dirname(files["fba"]), "_%s.eml" % label.replace(" ", "_"))
            open(p, "wb").write(bytes(m)); done.append(p)
        return "mail written as .eml for review (not sent): " + ", ".join(done)
    if mode != "send": raise RuntimeError("MAIL_MODE must be off, eml or send")
    if not cfg["pw"]: raise RuntimeError("GMAIL_APP_PASSWORD is missing in credentials.txt")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(cfg["user"], cfg["pw"].replace(" ", ""))
        for label, m in msgs: s.send_message(m); done.append(label + " -> " + m["To"])
    return "sent: " + "; ".join(done)
