from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from config import Config

# Human-readable Chinese labels for the status values that flow through
# EmailNotifier. The subject previously hardcoded "已开售", which was
# misleading for checker-failure alerts. Unknown statuses fall back to a
# generic label rather than echoing the raw status string into the subject.
_STATUS_LABELS = {
    "on_sale": "已开售",
    "not_on_sale": "未开售",
    "checker_failed": "检查器异常",
}


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, "未知状态")


class EmailNotifier:
    def __init__(self, config: Config):
        self.config = config

    def send(self, title: str, url: str, status: str) -> None:
        label = _status_label(status)
        subject = f"[开票提醒] {title} {label}"
        body = (
            f"演出：{title}\n"
            f"状态：{label}\n"
            f"链接：{url}\n"
        )

        # EMAIL_TO may contain a comma-separated list of recipients.
        recipients = [addr.strip() for addr in self.config.email_to.split(",") if addr.strip()]
        if not recipients:
            raise ValueError("EMAIL_TO is empty")

        msg = MIMEMultipart()
        msg["From"] = self.config.smtp_user
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            server.starttls()
            server.login(self.config.smtp_user, self.config.smtp_password)
            server.send_message(msg, to_addrs=recipients)
