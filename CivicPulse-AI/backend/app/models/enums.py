import enum


class UserRole(enum.StrEnum):
    citizen = "citizen"
    official = "official"
    admin = "admin"


class ProcessingStatus(enum.StrEnum):
    queued = "queued"
    processing = "processing"
    triaged = "triaged"
    needs_manual_triage = "needs_manual_triage"
    rejected = "rejected"


class IssueStatus(enum.StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    assigned = "assigned"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"
    reopened = "reopened"
    rejected = "rejected"


class CvStatus(enum.StrEnum):
    pending = "pending"
    done = "done"
    failed = "failed"
    skipped = "skipped"


class ModerationStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    flagged = "flagged"


class NotificationChannel(enum.StrEnum):
    inapp = "inapp"
    email = "email"


class CorrectionKind(enum.StrEnum):
    recategorize = "recategorize"
    detach = "detach"
    merge = "merge"
    priority_override = "priority_override"
    reject = "reject"


class AiJobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
