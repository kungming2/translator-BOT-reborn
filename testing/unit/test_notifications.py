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


def test_notifier_returns_structured_delivery_result():
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

    assert result.subscriber_count == 2
    assert result.already_contacted_count == 0
    assert result.eligible_count == 2
    assert result.attempted_count == 2
    assert result.sent_usernames == ["sent_user"]
    assert result.failed_usernames == ["blocked_user"]


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

    assert result.subscriber_count == 0
    assert result.attempted_count == 0
    assert result.sent_usernames == []
    assert result.failed_usernames == []
    assert db.conn_main.cursor_obj.executed[-1][1] == ("pt-BR",)


def test_notifier_reports_previously_contacted_and_failed_page_recipient():
    subscribers = [f"persian_user_{index}" for index in range(20)]
    db = _Db([("fa", username) for username in subscribers])
    reddit = SimpleNamespace(
        redditor=lambda username: SimpleNamespace(name=username),
    )
    ajo = SimpleNamespace(
        language_history=[],
        notified=subscribers[:19],
    )

    with (
        patch.object(notifications, "db", db),
        patch.object(notifications, "REDDIT", reddit),
        patch.object(notifications, "ajo_loader", return_value=ajo),
        patch.object(notifications, "message_send", return_value=False),
        patch.object(notifications, "action_counter"),
        patch.object(notifications, "record_activity_csv"),
        patch.object(notifications, "increment_runtime_metric"),
        patch.object(notifications, "check_url_extension", return_value=False),
        patch.object(notifications.random, "shuffle", lambda _items: None),
        patch.dict(
            notifications.SETTINGS,
            {
                "notifications_monthly_limit": 30,
                "notifications_user_limit": 30,
                "notifications_api_limiter_on": False,
                "notifications_rare_language_rate_threshold": 5,
                "unknown_language_default_rate": 1,
                "num_users_page": 5,
            },
        ),
    ):
        result = notifications.notifier(
            _lingvo(
                name="Persian",
                language_code_1="fa",
                language_code_3="fas",
                rate_monthly=22.09,
            ),
            _submission(),
            mode="page",
        )

    assert result.subscriber_count == 20
    assert result.already_contacted_count == 19
    assert result.eligible_count == 1
    assert result.attempted_count == 1
    assert result.sent_usernames == []
    assert result.failed_usernames == ["persian_user_19"]


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
