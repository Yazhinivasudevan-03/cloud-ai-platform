"""CloudAccountTimezone model: multi-timezone support for cloud accounts
(Phase 22). A CloudProviderAccount stores exactly one `region` on itself
(unchanged - a real backward-compatibility constraint, not an oversight),
but real accounts commonly have resources spread across multiple
regions/timezones (an AWS account with both eu-west-2/London and
ap-south-1/Mumbai deployments, for example). This table holds that
one-to-many relationship: any number of (region, timezone) entries per
account, each independently addressable.

`provider` is deliberately NOT duplicated here - it's read via the
relationship to `CloudProviderAccount.provider` at query/serialization
time, avoiding a second copy of the same fact that could drift out of
sync if the account's provider were ever corrected.

`timezone` is a plain IANA identifier string (e.g. "Europe/London",
"Asia/Kolkata") - never a raw UTC offset or a fixed-offset abbreviation,
since Daylight Saving Time (BST vs GMT, for example) means the correct
offset for a given IANA zone depends on which specific date/time you're
asking about, not the zone alone. The offset itself is never stored -
see app/utils/timezones.py, which computes it on demand via the stdlib
`zoneinfo` module (Python's own IANA tzdata), so it is always correct for
DST rather than a value that would silently go stale.
"""
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin


class CloudAccountTimezone(TimestampMixin, Base):
    __tablename__ = "cloud_account_timezones"
    __table_args__ = (
        UniqueConstraint(
            "cloud_provider_account_id", "region", "timezone",
            name="uq_cloud_account_timezone_region_tz",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cloud_provider_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cloud_provider_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    availability_zone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Human label for this regional presence, e.g. "London Production" -
    # deliberately distinct from the platform's existing Deployment.name
    # (a microservice instance), which is a different concept entirely.
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)

    cloud_provider_account: Mapped["CloudProviderAccount"] = relationship(
        "CloudProviderAccount", back_populates="timezones"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        "Deployment", back_populates="cloud_account_timezone"
    )
