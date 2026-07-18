"""Import every ORM model so they register on `Base.metadata`.

This module must be imported before Alembic autogeneration or
`Base.metadata.create_all()` is called, otherwise tables defined in
modules that were never imported would be silently skipped.
"""
from app.models.alert import Alert
from app.models.anomaly_detection import AnomalyDetection
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.cloud_cost import CloudCost
from app.models.cloud_provider_account import CloudProviderAccount
from app.models.deployment import Deployment
from app.models.failure_prediction import FailurePrediction
from app.models.log import Log
from app.models.metric import Metric
from app.models.microservice import Microservice
from app.models.notification import Notification
from app.models.optimization_recommendation import OptimizationRecommendation
from app.models.pod import Pod
from app.models.prediction import Prediction
from app.models.project import Project
from app.models.resource_usage import ResourceUsage
from app.models.setting import Setting
from app.models.user import Role, User, user_roles

__all__ = [
    "Alert",
    "AnomalyDetection",
    "ApiKey",
    "AuditLog",
    "CloudCost",
    "CloudProviderAccount",
    "Deployment",
    "FailurePrediction",
    "Log",
    "Metric",
    "Microservice",
    "Notification",
    "OptimizationRecommendation",
    "Pod",
    "Prediction",
    "Project",
    "ResourceUsage",
    "Role",
    "Setting",
    "User",
    "user_roles",
]
