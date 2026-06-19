import logging
from urllib.parse import quote, urlparse

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.translation import gettext as _


logger = logging.getLogger('judge.external_judge')


class ExternalJudgeError(Exception):
    user_message = _('External judge hiện không khả dụng, vui lòng thử lại sau')

    def __init__(self, message=None, *, status_code=None, response=None):
        super().__init__(message or self.user_message)
        self.status_code = status_code
        self.response = response


class ExternalJudgeConnectionError(ExternalJudgeError):
    user_message = _('External judge hiện không khả dụng, vui lòng thử lại sau')


class ExternalJudgeAuthError(ExternalJudgeError):
    user_message = _('Lỗi cấu hình external judge, vui lòng liên hệ admin')


class ExternalJudgeConfigurationError(ExternalJudgeError):
    user_message = _('Lỗi cấu hình external judge, vui lòng liên hệ admin')


class ExternalJudgeUpstreamError(ExternalJudgeError):
    user_message = _('OJ bên ngoài hiện không khả dụng')


class ExternalJudgeNotFoundError(ExternalJudgeError):
    user_message = _('Không tìm thấy bài trên external judge')


class ExternalJudgeBadRequestError(ExternalJudgeError):
    user_message = _('External judge từ chối yêu cầu này')


def user_safe_message(error):
    return getattr(error, 'user_message', ExternalJudgeError.user_message)


def _require_dict_payload(payload, context):
    if not isinstance(payload, dict):
        raise ExternalJudgeUpstreamError(_('External judge returned invalid %(context)s payload.') % {
            'context': context,
        })
    return payload


class ExternalJudgeClient:
    def __init__(self, config, *, timeout=None):
        if config is None:
            raise ExternalJudgeConfigurationError(_('External judge config is required.'))
        self.config = config
        self.base_url = str(getattr(config, 'base_url', '') or '').strip().rstrip('/')
        self.timeout = self._clean_timeout(
            timeout if timeout is not None else getattr(config, 'timeout_seconds', None),
        )
        self._validate_base_url()

    def _config_name(self):
        return getattr(self.config, 'name', '<unknown>')

    def _clean_timeout(self, value):
        try:
            timeout = float(value)
        except (TypeError, ValueError) as exc:
            raise ExternalJudgeConfigurationError(_('External judge timeout is invalid.')) from exc
        if timeout <= 0:
            raise ExternalJudgeConfigurationError(_('External judge timeout is invalid.'))
        return timeout

    def _validate_base_url(self):
        parsed = urlparse(self.base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ExternalJudgeConfigurationError(_('External judge base URL is invalid.'))
        if parsed.scheme == 'http' and not getattr(settings, 'EXTERNAL_JUDGE_ALLOW_HTTP', False):
            raise ExternalJudgeConfigurationError(_('External judge must use HTTPS in production.'))

    def _get_token(self):
        try:
            token = self.config.get_api_token()
        except (ImproperlyConfigured, ValidationError, ValueError, TypeError, UnicodeError) as exc:
            logger.exception(
                'External judge API token is not usable: config=%s',
                self._config_name(),
            )
            raise ExternalJudgeAuthError(_('External judge API token is invalid.')) from exc

        token = str(token or '').strip()
        if not token:
            raise ExternalJudgeAuthError(_('External judge API token is not configured.'))
        return token

    def _headers(self):
        return {
            'Authorization': 'Bearer %s' % self._get_token(),
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def _request(self, method, path, *, timeout=None, **kwargs):
        url = '%s%s' % (self.base_url, path)
        request_timeout = self._clean_timeout(timeout if timeout is not None else self.timeout)
        request_kwargs = dict(kwargs)
        source_present = False
        if isinstance(request_kwargs.get('json'), dict) and 'source' in request_kwargs['json']:
            source_present = True
        logger.info(
            'External judge request: method=%s config=%s path=%s source_present=%s',
            method,
            self._config_name(),
            path,
            source_present,
        )
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                timeout=request_timeout,
                **request_kwargs,
            )
        except ExternalJudgeError:
            raise
        except ValueError as exc:
            error_message = str(exc)
            logger.warning(
                'External judge request configuration error: config=%s path=%s error=%s',
                self._config_name(),
                path,
                error_message,
            )
            raise ExternalJudgeConfigurationError(_('External judge request configuration is invalid.')) from exc
        except requests.RequestException as exc:
            error_message = str(exc)
            logger.warning(
                'External judge connection error: config=%s path=%s error=%s',
                self._config_name(),
                path,
                error_message,
            )
            raise ExternalJudgeConnectionError(str(exc)) from exc

        logger.info(
            'External judge response: config=%s path=%s status=%s',
            self._config_name(),
            path,
            response.status_code,
        )
        if response.status_code == 401:
            raise ExternalJudgeAuthError(status_code=response.status_code, response=response)
        if response.status_code == 404:
            raise ExternalJudgeNotFoundError(status_code=response.status_code, response=response)
        if response.status_code == 502:
            raise ExternalJudgeUpstreamError(status_code=response.status_code, response=response)
        if 400 <= response.status_code < 500:
            raise ExternalJudgeBadRequestError(status_code=response.status_code, response=response)
        if response.status_code >= 500:
            raise ExternalJudgeUpstreamError(status_code=response.status_code, response=response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalJudgeUpstreamError(_('External judge returned invalid JSON.')) from exc

        if isinstance(payload, dict) and 'data' in payload:
            return payload['data']
        return payload

    def verify_connection(self):
        return self.get_ojs()

    def get_ojs(self):
        data = self._request('GET', '/api/v1/ojs')
        if isinstance(data, dict) and isinstance(data.get('items'), list):
            return data['items']
        return data

    def get_problem(self, oj, problem_id):
        return self._request(
            'GET',
            '/api/v1/problems/%s/%s' % (quote(str(oj), safe=''), quote(str(problem_id), safe='')),
        )

    def get_problem_statement(self, oj, problem_id):
        return self._request(
            'GET',
            '/api/v1/problems/%s/%s/statement' % (
                quote(str(oj), safe=''),
                quote(str(problem_id), safe=''),
            ),
        )

    def submit(self, oj, problem_id, language, source, open=True):
        return _require_dict_payload(self._request(
            'POST',
            '/api/v1/submissions',
            timeout=self.config.timeout_seconds,
            json={
                'oj': oj,
                'problemId': problem_id,
                'language': str(language),
                'source': source,
                'open': open,
            },
        ), _('submission'))

    def get_submission_status(self, submission_id):
        return _require_dict_payload(self._request(
            'GET',
            '/api/v1/submissions/%s/status' % quote(str(submission_id), safe=''),
            timeout=self.config.poll_timeout_seconds,
        ), _('submission status'))
