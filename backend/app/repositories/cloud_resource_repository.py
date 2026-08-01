"""Data-access layer for the CloudResource/CloudResourceMetric entities
(Phase 29's automatic-discovery persistence)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cloud_resource import CloudResource
from app.models.cloud_resource_metric import CloudResourceMetric
from app.repositories.base_repository import BaseRepository


class CloudResourceRepository(BaseRepository[CloudResource]):
    def __init__(self, db: Session):
        super().__init__(db, CloudResource)

    def get_by_identity(
        self, cloud_provider_account_id: int, resource_type: str, region: str, external_id: str
    ) -> CloudResource | None:
        stmt = select(CloudResource).where(
            CloudResource.cloud_provider_account_id == cloud_provider_account_id,
            CloudResource.resource_type == resource_type,
            CloudResource.region == region,
            CloudResource.external_id == external_id,
        )
        return self.db.scalars(stmt).first()

    def list_for_account(
        self,
        cloud_provider_account_id: int,
        resource_type: str | None = None,
        active_only: bool = True,
    ) -> list[CloudResource]:
        stmt = select(CloudResource).where(
            CloudResource.cloud_provider_account_id == cloud_provider_account_id
        )
        if resource_type is not None:
            stmt = stmt.where(CloudResource.resource_type == resource_type)
        if active_only:
            stmt = stmt.where(CloudResource.is_active.is_(True))
        stmt = stmt.order_by(CloudResource.resource_type, CloudResource.name)
        return list(self.db.scalars(stmt).all())

    def list_active_ids_for_scope(
        self, cloud_provider_account_id: int, resource_type: str, region: str
    ) -> set[int]:
        """Every currently-active resource id for one account+type+region -
        used to compute which previously-seen resources a fresh discovery
        pass no longer observed (see mark_inactive_except below)."""
        stmt = select(CloudResource.id).where(
            CloudResource.cloud_provider_account_id == cloud_provider_account_id,
            CloudResource.resource_type == resource_type,
            CloudResource.region == region,
            CloudResource.is_active.is_(True),
        )
        return set(self.db.scalars(stmt).all())

    def mark_inactive_except(
        self, cloud_provider_account_id: int, resource_type: str, region: str, seen_ids: set[int]
    ) -> None:
        """The generic appear/disappear mechanism (requirement 9): any
        resource that was active for this account+type+region before this
        discovery pass, but wasn't seen in it, has been terminated/deleted
        in the real provider - flip it inactive rather than deleting the
        row, preserving history."""
        previously_active_ids = self.list_active_ids_for_scope(cloud_provider_account_id, resource_type, region)
        stale_ids = previously_active_ids - seen_ids
        if not stale_ids:
            return
        stmt = select(CloudResource).where(CloudResource.id.in_(stale_ids))
        for resource in self.db.scalars(stmt).all():
            resource.is_active = False
        self.db.commit()

    def upsert(
        self,
        *,
        user_id: int,
        cloud_provider_account_id: int,
        provider: str,
        resource_type: str,
        external_id: str,
        name: str,
        region: str,
        status: str,
        availability_zone: str | None = None,
        instance_type: str | None = None,
        public_ip: str | None = None,
        private_ip: str | None = None,
        tags_json: str | None = None,
        extra_json: str | None = None,
        seen_at: datetime,
    ) -> CloudResource:
        existing = self.get_by_identity(cloud_provider_account_id, resource_type, region, external_id)
        if existing is None:
            resource = CloudResource(
                user_id=user_id,
                cloud_provider_account_id=cloud_provider_account_id,
                provider=provider,
                resource_type=resource_type,
                external_id=external_id,
                name=name,
                region=region,
                availability_zone=availability_zone,
                status=status,
                instance_type=instance_type,
                public_ip=public_ip,
                private_ip=private_ip,
                tags_json=tags_json,
                extra_json=extra_json,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                is_active=True,
            )
            self.db.add(resource)
            self.db.commit()
            self.db.refresh(resource)
            return resource

        existing.name = name
        existing.status = status
        existing.availability_zone = availability_zone
        existing.instance_type = instance_type
        existing.public_ip = public_ip
        existing.private_ip = private_ip
        existing.tags_json = tags_json
        existing.extra_json = extra_json
        existing.last_seen_at = seen_at
        existing.is_active = True
        self.db.commit()
        self.db.refresh(existing)
        return existing

    def add_metric(self, metric: CloudResourceMetric) -> CloudResourceMetric:
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get_latest_metric(self, cloud_resource_id: int) -> CloudResourceMetric | None:
        stmt = (
            select(CloudResourceMetric)
            .where(CloudResourceMetric.cloud_resource_id == cloud_resource_id)
            .order_by(CloudResourceMetric.recorded_at.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()
