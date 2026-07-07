from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from config import Config


class EmailNotifier:
    def __init__(self, config: Config):
        self.config = config

    def send(self, title: str, url: str, status: str) -> None:
        subject = f"[开票提醒] {title} 已开售"
        body = (
            f"演出：{title}\n"
            f"状态：{'已开售' if status == 'on_sale' else status}\n"
            f"链接：{url}\n"
        )

        msg = MIMEMultipart()
        msg["From"] = self.config.smtp_user
        msg["To"] = self.config.email_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            server.starttls()
            server.login(self.config.smtp_user, self.config.smtp_password)
            server.send_message(msg)
