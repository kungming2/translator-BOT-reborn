import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

from models.lingvo import Lingvo

_previous_startup_module = sys.modules.get("reddit.startup")
_startup_stub = types.ModuleType("reddit.startup")
_startup_stub.STATE = SimpleNamespace(recent_submitters=[])
sys.modules["reddit.startup"] = _startup_stub
notifications = importlib.import_module("reddit.notifications")

if _previous_startup_module is None:
    del sys.modules["reddit.startup"]
else:
    sys.modules["reddit.startup"] = _previous_startup_module


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, query, params=()):
        self.executed.append((query, params))
        return self

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_obj = _Cursor(rows)

    def cursor(self):
        return self.cursor_obj


class _Db:
    def __init__(self, rows):
        self.conn_main = _Connection(rows)


def _submission() -> SimpleNamespace:
    return SimpleNamespace(
        id="post123",
        title="[Chinese > English] Example",
        permalink="/r/translator/comments/post123/example/",
        author=SimpleNamespace(name="op_user"),
        over_18=False,
        url="https://reddit.example/post123",
    )


def _lingvo(**kwargs) -> Lingvo:
    defaults = {
        "name": "Chinese",
        "language_code_1": "zh",
        "language_code_3": "zho",
        "greetings": "Hello",
        "rate_monthly": 1,
    }
    defaults.update(kwargs)
    return Lingvo(**defaults)


def test_notifier_returns_only_successfully_sent_usernames():
    db = _Db([("zh", "sent_user"), ("zh", "blocked_user")])
    reddit = SimpleNamespace(
        redditor=lambda username: SimpleNamespace(name=username),
    )

    def fake_message_send(*, redditor_obj, **_kwargs):
        return redditor_obj.name == "sent_user"

    with (
        patch.object(notifications, "db", db),
        patch.object(notifications, "REDDIT", reddit),
        patch.object(notifications, "ajo_loader", return_value=None),
        patch.object(notifications, "message_send", side_effect=fake_message_send),
        patch.object(notifications, "_update_user_notification_count"),
        patch.object(notifications, "action_counter"),
        patch.object(notifications, "record_activity_csv"),
        patch.object(notifications, "increment_runtime_metric"),
        patch.object(notifications, "check_url_extension", return_value=False),
        patch.object(notifications.random, "shuffle", lambda _items: None),
        patch.dict(
            notifications.SETTINGS,
            {
                "notifications_monthly_limit": 10,
                "notifications_user_limit": 10,
                "notifications_api_limiter_on": False,
                "unknown_language_default_rate": 1,
                "num_users_page": 5,
            },
        ),
    ):
        result = notifications.notifier(_lingvo(), _submission())

    assert result == ["sent_user"]


def test_notifier_uses_alpha2_country_code_for_regional_subscription_query():
    db = _Db([])

    with (
        patch.object(notifications, "db", db),
        patch.object(notifications, "ajo_loader", return_value=None),
        patch.object(notifications, "country_converter", return_value=("BR", "Brazil")),
        patch.object(notifications, "_notifier_specific_language_filter", return_value=[]),
    ):
        result = notifications.notifier(
            _lingvo(
                name="Portuguese",
                language_code_1="pt",
                language_code_3="por",
                country="Brazil",
            ),
            _submission(),
        )

    assert result == []
    assert db.conn_main.cursor_obj.executed[-1][1] == ("pt-BR",)


def test_notification_rate_limiter_uses_configured_rare_language_threshold():
    subscribers = [f"user_{index}" for index in range(10)]

    with patch.dict(
        notifications.SETTINGS,
        {
            "notifications_api_limiter_on": False,
            "notifications_rare_language_rate_threshold": 7,
            "notifications_user_limit": 10,
        },
    ):
        selected = notifications._notification_rate_limiter(
            subscribers,
            _lingvo(rate_monthly=6),
            monthly_limit=1,
        )

    assert selected == sorted(subscribers)
