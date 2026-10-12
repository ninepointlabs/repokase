"""Typed GitHub API failures the UI knows how to explain."""

from __future__ import annotations

from .. import config


class ApiError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class NetworkError(ApiError):
    def __init__(self, detail: str = ""):
        super().__init__("Could not reach GitHub. Showing cached data where available.")
        self.detail = detail


class AuthExpired(ApiError):
    def __init__(self):
        super().__init__("Your GitHub sign-in has expired or was revoked. Please sign in again.", 401)


class ScopeMissing(ApiError):
    def __init__(self, needed: set[str]):
        self.needed = needed
        super().__init__(f"This needs extra GitHub permission: {', '.join(sorted(needed))}.", 403)


class OrgBlocked(ApiError):
    """An organization policy, not the user's role, refused the request.

    `url` is the GitHub page that fixes it, so the UI can offer one button.
    """

    def __init__(self, message: str, url: str | None, org: str | None = None):
        self.url = url
        self.org = org
        super().__init__(message, 403)


class SsoRequired(OrgBlocked):
    def __init__(self, url: str | None, org: str | None = None):
        who = f"the {org} organization" if org else "this organization"
        super().__init__(f"{who.capitalize()} requires SAML single sign-on for this token.", url, org)


class AppRestricted(OrgBlocked):
    """The organization has OAuth app access restrictions and hasn't approved Repokase."""

    def __init__(self, org: str | None):
        who = f"The {org} organization" if org else "This organization"
        super().__init__(
            f"{who} restricts third-party apps and hasn't approved Repokase.", config.app_access_url(), org
        )


class RateLimited(ApiError):
    def __init__(self, reset_at: float | None):
        self.reset_at = reset_at
        super().__init__("GitHub API rate limit reached.", 403)


class NotFound(ApiError):
    def __init__(self, what: str = "resource"):
        super().__init__(f"GitHub could not find that {what}, or you no longer have access.", 404)


class GraphQLError(ApiError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        msg = "; ".join(e.get("message", "unknown error") for e in errors) or "GraphQL error"
        super().__init__(msg)
