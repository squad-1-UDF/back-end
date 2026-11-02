"""Contrato HTTP com autenticação/sessão simuladas, sem banco de dados."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from apps.accounts.api import authenticate_identifier

BAD_CSRF_TOKEN = "b" * 32


def fake_user(*, active=True):
    return SimpleNamespace(pk=7, is_active=active, is_authenticated=True)


class AuthApiTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.csrf_url = reverse("auth-csrf")
        self.login_url = reverse("auth-login")
        self.logout_url = reverse("auth-logout")
        self.me_url = reverse("auth-me")

    def csrf(self):
        response = self.client.get(self.csrf_url)
        self.assertEqual(response.status_code, 204)
        self.assertIn("csrftoken", self.client.cookies)
        return {"HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value}

    def test_csrf_cookie_is_issued_to_anonymous_client(self):
        response = self.client.get(self.csrf_url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertIn("csrftoken", response.cookies)
        self.assertNotIn("sessionid", response.cookies)
        self.assertIn("Cookie", response.headers["Vary"])
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_drf_view_is_exempt_at_entry_but_login_still_requires_csrf(self):
        self.assertTrue(resolve(self.login_url).func.csrf_exempt)
        with patch("apps.accounts.api.authenticate_identifier") as authenticate_mock:
            response = self.post_login({"identifier": "ana", "password": "segredo"})
        self.assertEqual(response.status_code, 403)
        authenticate_mock.assert_not_called()

    def post_login(self, payload, **extra):
        return self.client.post(
            self.login_url,
            data=payload,
            content_type="application/json",
            **extra,
        )

    def test_login_requires_csrf_even_when_anonymous(self):
        with patch("apps.accounts.api.authenticate_identifier") as authenticate_mock:
            response = self.post_login({"identifier": "ana", "password": "segredo"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "CSRF inválido ou ausente."})
        authenticate_mock.assert_not_called()

    def test_login_rejects_invalid_payload_without_authentication(self):
        invalid = [
            {},
            {"identifier": "ana"},
            {"identifier": "", "password": "segredo"},
            {"identifier": "   ", "password": "segredo"},
            {"identifier": "ana", "password": ""},
            {"identifier": 42, "password": "segredo"},
            {"identifier": "ana", "password": 42},
            {"identifier": "ana", "password": "segredo", "email": "x@y.z"},
            ["ana", "segredo"],
        ]
        with patch("apps.accounts.api.authenticate_identifier") as authenticate_mock:
            for payload in invalid:
                with self.subTest(payload=payload):
                    response = self.post_login(payload, **self.csrf())
                    self.assertEqual(response.status_code, 400)
            authenticate_mock.assert_not_called()

    def test_login_rejects_malformed_json_and_non_json_content(self):
        with patch("apps.accounts.api.authenticate_identifier") as authenticate_mock:
            invalid_json = self.client.post(
                self.login_url,
                data="{",
                content_type="application/json",
                **self.csrf(),
            )
            wrong_media = self.client.post(
                self.login_url,
                data="identifier=ana&password=segredo",
                content_type="application/x-www-form-urlencoded",
                **self.csrf(),
            )
            authenticate_mock.assert_not_called()
        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(wrong_media.status_code, 415)

    def test_login_rejects_cookie_without_matching_csrf_header(self):
        self.csrf()
        with patch("apps.accounts.api.authenticate_identifier") as authenticate_mock:
            response = self.post_login({"identifier": "ana", "password": "segredo"})
            authenticate_mock.assert_not_called()
        self.assertEqual(response.status_code, 403)

    def test_login_rejects_incorrect_csrf_token(self):
        self.csrf()
        with patch("apps.accounts.api.authenticate_identifier") as authenticate_mock:
            response = self.post_login(
                {"identifier": "ana", "password": "segredo"},
                HTTP_X_CSRFTOKEN=BAD_CSRF_TOKEN,
            )
            authenticate_mock.assert_not_called()
        self.assertEqual(response.status_code, 403)

    @override_settings(CSRF_TRUSTED_ORIGINS=[])
    def test_login_rejects_untrusted_origin_with_valid_token(self):
        with patch("apps.accounts.api.authenticate_identifier") as authenticate_mock:
            response = self.post_login(
                {"identifier": "ana", "password": "segredo"},
                HTTP_ORIGIN="https://untrusted.example",
                **self.csrf(),
            )
            authenticate_mock.assert_not_called()
        self.assertEqual(response.status_code, 403)

    def test_login_bad_credentials_and_inactive_user_are_indistinguishable(self):
        payload = {"identifier": "ana", "password": "incorreta"}
        responses = []
        for user in (None, fake_user(active=False)):
            with self.subTest(user=user):
                with (
                    patch(
                        "apps.accounts.api.authenticate_identifier", return_value=user
                    ),
                    patch("apps.accounts.api.login") as login_mock,
                ):
                    response = self.post_login(payload, **self.csrf())
                    login_mock.assert_not_called()
                responses.append((response.status_code, response.json()))
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(responses[0][0], 401)

    def test_login_success_returns_only_id(self):
        user = fake_user()
        with (
            patch("apps.accounts.api.authenticate_identifier", return_value=user),
            patch("apps.accounts.api.login") as login_mock,
        ):
            response = self.post_login(
                {"identifier": "ana", "password": "segredo"}, **self.csrf()
            )
            login_mock.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user": {"id": 7}})

    def test_authentication_maps_identifier_to_configured_username_field(self):
        request = SimpleNamespace(_request=object())
        user_model = SimpleNamespace(USERNAME_FIELD="institutional_id")
        with (
            patch("apps.accounts.api.get_user_model", return_value=user_model),
            patch("apps.accounts.api.authenticate", return_value=None) as auth_mock,
        ):
            authenticate_identifier(request, "matricula", "segredo")
        auth_mock.assert_called_once_with(
            request._request, institutional_id="matricula", password="segredo"
        )

    def test_anonymous_me_and_logout_return_403_with_session_authentication(self):
        me = self.client.get(self.me_url)
        logout_response = self.client.post(
            self.logout_url,
            data={},
            content_type="application/json",
            **self.csrf(),
        )
        self.assertEqual(me.status_code, 403)
        self.assertEqual(logout_response.status_code, 403)

    def test_me_returns_only_id_for_authenticated_request(self):
        with patch(
            "django.contrib.auth.middleware.auth.get_user", return_value=fake_user()
        ):
            response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": 7})

    def test_logout_requires_csrf_for_authenticated_request(self):
        with (
            patch(
                "django.contrib.auth.middleware.auth.get_user", return_value=fake_user()
            ),
            patch("apps.accounts.api.logout") as logout_mock,
        ):
            response = self.client.post(
                self.logout_url, data={}, content_type="application/json"
            )
            logout_mock.assert_not_called()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "CSRF inválido ou ausente."})

    def test_logout_rejects_incorrect_csrf_token(self):
        self.csrf()
        with (
            patch(
                "django.contrib.auth.middleware.auth.get_user", return_value=fake_user()
            ),
            patch("apps.accounts.api.logout") as logout_mock,
        ):
            response = self.client.post(
                self.logout_url,
                data={},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=BAD_CSRF_TOKEN,
            )
            logout_mock.assert_not_called()
        self.assertEqual(response.status_code, 403)

    @override_settings(CSRF_TRUSTED_ORIGINS=[])
    def test_logout_rejects_untrusted_origin_with_valid_token(self):
        with (
            patch(
                "django.contrib.auth.middleware.auth.get_user", return_value=fake_user()
            ),
            patch("apps.accounts.api.logout") as logout_mock,
        ):
            response = self.client.post(
                self.logout_url,
                data={},
                content_type="application/json",
                HTTP_ORIGIN="https://untrusted.example",
                **self.csrf(),
            )
            logout_mock.assert_not_called()
        self.assertEqual(response.status_code, 403)

    def test_logout_calls_django_logout_with_csrf(self):
        with (
            patch(
                "django.contrib.auth.middleware.auth.get_user", return_value=fake_user()
            ),
            patch("apps.accounts.api.logout") as logout_mock,
        ):
            response = self.client.post(
                self.logout_url,
                data={},
                content_type="application/json",
                **self.csrf(),
            )
            logout_mock.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "signed_out"})

    def test_logout_accepts_empty_body(self):
        with (
            patch(
                "django.contrib.auth.middleware.auth.get_user", return_value=fake_user()
            ),
            patch("apps.accounts.api.logout") as logout_mock,
        ):
            response = self.client.generic(
                "POST", self.logout_url, data=b"", **self.csrf()
            )
            logout_mock.assert_called_once()
        self.assertEqual(response.status_code, 200)

    def test_logout_rejects_nonempty_body(self):
        with (
            patch(
                "django.contrib.auth.middleware.auth.get_user", return_value=fake_user()
            ),
            patch("apps.accounts.api.logout") as logout_mock,
        ):
            response = self.client.post(
                self.logout_url,
                data={"extra": True},
                content_type="application/json",
                **self.csrf(),
            )
            logout_mock.assert_not_called()
        self.assertEqual(response.status_code, 400)

    def test_disallowed_methods(self):
        self.assertEqual(
            self.client.post(self.csrf_url, **self.csrf()).status_code, 405
        )
        self.assertEqual(self.client.get(self.login_url).status_code, 405)
        with patch(
            "django.contrib.auth.middleware.auth.get_user", return_value=fake_user()
        ):
            self.assertEqual(self.client.get(self.logout_url).status_code, 405)
            self.assertEqual(
                self.client.post(self.me_url, data={}, **self.csrf()).status_code, 405
            )
