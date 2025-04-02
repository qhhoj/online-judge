import smtplib
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPEmailBackend

class EmailBackend(DjangoSMTPEmailBackend):
    """
    Custom email backend for Django 3.2 that works around
    Python 3.12's removal of keyfile and certfile parameters in SMTP.starttls().
    """

    def open(self):
        """
        Open a network connection and log in if necessary.
        This overrides the parent's open() method to call starttls() without
        passing keyfile and certfile.
        """
        if self.connection:
            return False

        connection = None
        try:
            # Ensure local_hostname is set, defaulting to None if it isn't.
            local_hostname = getattr(self, 'local_hostname', None)
            connection = self.connection_class(
                self.host,
                self.port,
                local_hostname=local_hostname,
                timeout=self.timeout,
            )
            connection.ehlo()
            if self.use_tls:
                # Call starttls without keyfile and certfile parameters.
                connection.starttls()
                connection.ehlo()
            if self.username and self.password:
                connection.login(self.username, self.password)
            self.connection = connection
            return True
        except Exception:
            if connection:
                connection.close()
            raise

