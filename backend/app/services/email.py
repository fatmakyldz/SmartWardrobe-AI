"""Transactional email behind one function: send(template, to, vars, lang).

Resend when RESEND_API_KEY is set; otherwise the fake backend, which keeps messages in OUTBOX and logs
the link (local runs, tests). Sending never raises into a request: a failure is logged.
"""

import html
import logging
from dataclasses import dataclass

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"

# subject, intro line, button label, footer — {link} and {name} are filled in.
TEMPLATES: dict[str, dict[str, tuple[str, str, str, str]]] = {
    "verify_email": {
        "en": ("Confirm your email for SmartWardrobe",
               "Hi{name}, confirm your email address to turn on outfit suggestions and photo tagging.",
               "Confirm email",
               "The link works for 24 hours. If you didn't sign up, you can ignore this email."),
        "tr": ("SmartWardrobe için e-postanı doğrula",
               "Merhaba{name}, kombin önerilerini ve fotoğraf etiketlemeyi açmak için e-posta adresini doğrula.",
               "E-postamı doğrula",
               "Bağlantı 24 saat geçerli. Kaydolmadıysan bu e-postayı görmezden gelebilirsin."),
    },
    "reset_password": {
        "en": ("Reset your SmartWardrobe password",
               "Hi{name}, someone (hopefully you) asked to reset your password.",
               "Choose a new password",
               "The link works for 1 hour and only once. If you didn't ask for this, ignore this email; your password stays the same."),
        "tr": ("SmartWardrobe şifreni sıfırla",
               "Merhaba{name}, şifreni sıfırlamak için bir istek aldık (umarız sendin).",
               "Yeni şifre belirle",
               "Bağlantı 1 saat ve yalnız bir kez geçerli. İstemediysen bu e-postayı görmezden gel; şifren değişmez."),
    },
}
OPEN_IN_APP = {"en": "On your phone with the app installed: {app_link}", "tr": "Telefonunda uygulama yüklüyse: {app_link}"}


@dataclass
class Message:
    to: str
    subject: str
    text: str
    html: str
    template: str
    link: str


OUTBOX: list[Message] = []


def render(template: str, lang: str, link: str, app_link: str, name: str = "") -> tuple[str, str, str]:
    lang = "tr" if lang == "tr" else "en"
    subject, intro, button, footer = TEMPLATES[template][lang]
    intro = intro.format(name=f" {name}" if name else "")
    in_app = OPEN_IN_APP[lang].format(app_link=app_link)
    text = f"{intro}\n\n{button}: {link}\n\n{in_app}\n\n{footer}\n"
    e = html.escape
    body = (
        f'<div style="font-family:system-ui,sans-serif;max-width:480px;margin:auto;color:#2a1b26">'
        f"<p>{e(intro)}</p>"
        f'<p><a href="{e(link)}" style="display:inline-block;padding:12px 20px;border-radius:10px;'
        f'background:#4b2e45;color:#fff;text-decoration:none">{e(button)}</a></p>'
        f'<p style="font-size:13px;color:#6b5a66">{e(in_app)}</p>'
        f'<p style="font-size:13px;color:#6b5a66">{e(footer)}</p></div>'
    )
    return subject, text, body


def links(path: str, token: str) -> tuple[str, str]:
    """(web link, app deep link) for /auth/verify or /auth/reset."""
    s = get_settings()
    return f"{s.app_url.rstrip('/')}/auth/{path}?token={token}", f"{s.app_scheme}://auth/{path}?token={token}"


def send(template: str, to: str, vars: dict, lang: str = "en") -> bool:
    """vars: link, app_link, name (optional). Returns whether the provider accepted the message."""
    subject, text, body = render(template, lang, vars["link"], vars["app_link"], vars.get("name", ""))
    s = get_settings()
    if not s.resend_api_key:
        OUTBOX.append(Message(to, subject, text, body, template, vars["link"]))
        if s.database_url.startswith("sqlite"):  # the link is a credential: logged only on local runs
            log.info("email (fake backend) %s → %s: %s", template, to, vars["link"])
        else:
            log.warning("RESEND_API_KEY is not set: %s email to a user was not sent", template)
        return True
    try:
        r = httpx.post(RESEND_URL, timeout=10.0, headers={"Authorization": f"Bearer {s.resend_api_key}"},
                       json={"from": s.email_from, "to": [to], "subject": subject, "text": text, "html": body})
        if r.status_code >= 300:
            log.warning("resend refused %s: %s %s", template, r.status_code, r.text[:200])
            return False
        return True
    except httpx.HTTPError:
        log.warning("resend unreachable for %s", template, exc_info=True)
        return False
