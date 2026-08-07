import dataclasses
from datetime import datetime
from typing import Optional, List, Dict, Any

# Application States
APP_STATE_DRAFT = "DRAFT"
APP_STATE_READY = "READY_FOR_APPROVAL"
APP_STATE_APPROVED = "APPROVED"
APP_STATE_SUBMITTED = "SUBMITTED"
APP_STATE_ACCEPTED = "ACCEPTED"
APP_STATE_REJECTED = "REJECTED"
APP_STATE_COMPLETED = "COMPLETED"

# Payment States
PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"
PAYMENT_PENDING = "PAYMENT_PENDING"
PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"

@dataclasses.dataclass
class Opportunity:
    id: str
    platform: str
    title: str
    url: str
    description: str = ""
    
    # Reward Information
    reward: Optional[float] = None
    currency: str = "USD"
    reward_verified: bool = False
    reward_source: str = "unknown"
    reward_evidence: str = ""
    
    deadline: Optional[str] = None
    skills: List[str] = dataclasses.field(default_factory=list)
    
    # AI Evaluation Fields
    difficulty: int = 0
    ai_suitable: bool = False
    estimated_hours: float = 0.0
    success_probability: int = 0
    profit_score: int = 0
    evaluation_decision: str = ""
    evaluation_reason: str = ""
    proposal: str = ""
    proposal_status: str = ""
    failure_reason: str = ""
    proposal_exists: bool = False
    
    # Access and Control
    eligibility: str = "unknown"
    automation_allowed: bool = False
    
    # Lifecycle
    status: str = APP_STATE_DRAFT
    discovered_at: str = dataclasses.field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Opportunity":
        # Extract fields that are valid for the Opportunity class
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
