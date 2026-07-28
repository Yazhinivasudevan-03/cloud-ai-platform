"""Self-service cloud provider account endpoints: every user configures and
manages only their own accounts. No role restriction beyond being an
authenticated, active user, and no limit on how many accounts a user may
register - consistent with every other self-service resource (e.g.
Notifications)."""
from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session

from app.authentication.dependencies import get_current_active_user
from app.controllers.cloud_account_alert_threshold_controller import (
    CloudAccountAlertThresholdController,
)
from app.controllers.cloud_account_timezone_controller import CloudAccountTimezoneController
from app.controllers.cloud_provider_account_controller import CloudProviderAccountController
from app.database.session import get_db
from app.models.user import User
from app.schemas.alert import AlertRead
from app.schemas.cloud_account_alert_threshold import (
    CloudAccountAlertThresholdRead,
    CloudAccountAlertThresholdUpdate,
)
from app.schemas.cloud_account_timezone import (
    CloudAccountTimezoneCreate,
    CloudAccountTimezoneRead,
    CloudAccountTimezoneUpdate,
)
from app.schemas.cloud_provider_account import (
    CloudAccountDeploymentSummary,
    CloudProviderAccountCreate,
    CloudProviderAccountRead,
    CloudProviderAccountUpdate,
)
from app.schemas.cloud_region import CloudAccountRegionsRead, SelectRegionRequest
from app.schemas.common import ErrorResponse, PaginatedResponse

router = APIRouter(prefix="/cloud-provider-accounts", tags=["Cloud Provider Accounts"])


@router.post(
    "",
    response_model=CloudProviderAccountRead,
    status_code=201,
    summary="Register a new cloud provider account for the current user",
    responses={409: {"model": ErrorResponse, "description": "Account name already in use by this user"}},
)
def create_cloud_provider_account(
    payload: CloudProviderAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudProviderAccountRead:
    return CloudProviderAccountController(db).create(current_user.id, payload)


@router.get(
    "",
    response_model=PaginatedResponse[CloudProviderAccountRead],
    summary="List the current user's own cloud provider accounts (paginated, filterable by provider)",
)
def list_my_cloud_provider_accounts(
    provider: str | None = Query(default=None, description="e.g. aws, azure, gcp"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PaginatedResponse[CloudProviderAccountRead]:
    return CloudProviderAccountController(db).list_for_user(
        current_user.id, provider, page, page_size
    )


@router.get(
    "/{account_id}",
    response_model=CloudProviderAccountRead,
    summary="Get one of the current user's own cloud provider accounts",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
    },
)
def get_my_cloud_provider_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudProviderAccountRead:
    return CloudProviderAccountController(db).get_own(account_id, current_user.id)


@router.put(
    "/{account_id}",
    response_model=CloudProviderAccountRead,
    summary="Update one of the current user's own cloud provider accounts",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
        409: {"model": ErrorResponse, "description": "Account name already in use by this user"},
    },
)
def update_my_cloud_provider_account(
    account_id: int,
    payload: CloudProviderAccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudProviderAccountRead:
    return CloudProviderAccountController(db).update(account_id, current_user.id, payload)


@router.delete(
    "/{account_id}",
    status_code=204,
    summary="Delete one of the current user's own cloud provider accounts",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
    },
)
def delete_my_cloud_provider_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    CloudProviderAccountController(db).delete(account_id, current_user.id)


@router.get(
    "/{account_id}/deployments",
    response_model=list[CloudAccountDeploymentSummary],
    summary=(
        "List the deployments linked to one of the current user's own cloud provider accounts, "
        "each with its latest synced resource usage (CPU/memory/network) - the consolidated "
        "'at a glance' usage view"
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
    },
)
def list_cloud_provider_account_deployments(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[CloudAccountDeploymentSummary]:
    return CloudProviderAccountController(db).list_linked_deployments(account_id, current_user.id)


@router.get(
    "/{account_id}/alerts",
    response_model=list[AlertRead],
    summary=(
        "List active alerts for deployments linked to one of the current user's own cloud "
        "provider accounts - this account's own alert feed, distinct from the platform-wide "
        "/alerts listing"
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
    },
)
def list_cloud_provider_account_alerts(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[AlertRead]:
    return CloudProviderAccountController(db).list_active_alerts(account_id, current_user.id)


@router.get(
    "/{account_id}/alert-thresholds",
    response_model=CloudAccountAlertThresholdRead,
    summary=(
        "Get one of the current user's own cloud provider accounts' CPU/memory alert "
        "threshold overrides (null fields fall back to the platform-wide default)"
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
    },
)
def get_cloud_provider_account_alert_thresholds(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudAccountAlertThresholdRead:
    return CloudAccountAlertThresholdController(db).get(account_id, current_user.id)


@router.put(
    "/{account_id}/alert-thresholds",
    response_model=CloudAccountAlertThresholdRead,
    summary="Update one of the current user's own cloud provider accounts' CPU/memory alert threshold overrides",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
        422: {"model": ErrorResponse, "description": "Thresholds are not in strictly ascending order"},
    },
)
def update_cloud_provider_account_alert_thresholds(
    account_id: int,
    payload: CloudAccountAlertThresholdUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudAccountAlertThresholdRead:
    return CloudAccountAlertThresholdController(db).update(account_id, current_user.id, payload)


@router.get(
    "/{account_id}/timezones",
    response_model=list[CloudAccountTimezoneRead],
    summary=(
        "List one of the current user's own cloud provider accounts' configured deployment "
        "timezones (Phase 22) - the same account can have resources across multiple "
        "regions/timezones, e.g. an AWS account with both London and Mumbai deployments"
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
    },
)
def list_cloud_provider_account_timezones(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[CloudAccountTimezoneRead]:
    return CloudAccountTimezoneController(db).list_for_account(account_id, current_user.id)


@router.post(
    "/{account_id}/timezones",
    response_model=CloudAccountTimezoneRead,
    status_code=201,
    summary="Add a deployment timezone entry to one of the current user's own cloud provider accounts",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
        409: {"model": ErrorResponse, "description": "This region/timezone combination already exists for this account"},
        422: {"model": ErrorResponse, "description": "Not a valid IANA timezone identifier"},
    },
)
def create_cloud_provider_account_timezone(
    account_id: int,
    payload: CloudAccountTimezoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudAccountTimezoneRead:
    return CloudAccountTimezoneController(db).create(account_id, current_user.id, payload)


@router.put(
    "/{account_id}/timezones/{timezone_id}",
    response_model=CloudAccountTimezoneRead,
    summary="Update one of the current user's own cloud provider accounts' deployment timezone entries",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account or timezone entry not found"},
        422: {"model": ErrorResponse, "description": "Not a valid IANA timezone identifier"},
    },
)
def update_cloud_provider_account_timezone(
    account_id: int,
    timezone_id: int,
    payload: CloudAccountTimezoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudAccountTimezoneRead:
    return CloudAccountTimezoneController(db).update(account_id, timezone_id, current_user.id, payload)


@router.delete(
    "/{account_id}/timezones/{timezone_id}",
    status_code=204,
    summary="Delete one of the current user's own cloud provider accounts' deployment timezone entries",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account or timezone entry not found"},
    },
)
def delete_cloud_provider_account_timezone(
    account_id: int,
    timezone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    CloudAccountTimezoneController(db).delete(account_id, timezone_id, current_user.id)


@router.get(
    "/{account_id}/regions",
    response_model=CloudAccountRegionsRead,
    summary=(
        "Get one of the current user's own cloud provider accounts' discovered regions "
        "(Phase 25) - regions are always discovered live via the provider's own API, "
        "never hardcoded; an account synced for the first time triggers one live call"
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
        422: {"model": ErrorResponse, "description": "Region discovery failed (bad credentials, provider outage, etc.)"},
    },
)
def get_cloud_provider_account_regions(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudAccountRegionsRead:
    return CloudProviderAccountController(db).get_regions(account_id, current_user.id)


@router.post(
    "/{account_id}/refresh-regions",
    response_model=CloudAccountRegionsRead,
    summary="Force a live re-discovery of one of the current user's own cloud provider accounts' regions",
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
        422: {"model": ErrorResponse, "description": "Region discovery failed (bad credentials, provider outage, etc.)"},
    },
)
def refresh_cloud_provider_account_regions(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudAccountRegionsRead:
    return CloudProviderAccountController(db).refresh_regions(account_id, current_user.id)


@router.patch(
    "/{account_id}/region",
    response_model=CloudProviderAccountRead,
    summary=(
        "Switch one of the current user's own cloud provider accounts' currently selected "
        "region (or 'all' to aggregate) without reconnecting the account"
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Not this user's account"},
        404: {"model": ErrorResponse, "description": "Account not found"},
        422: {"model": ErrorResponse, "description": "Not one of this account's discovered regions"},
    },
)
def update_cloud_provider_account_region(
    account_id: int,
    payload: SelectRegionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CloudProviderAccountRead:
    return CloudProviderAccountController(db).update_region(account_id, current_user.id, payload.selected_region)
