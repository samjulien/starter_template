from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

class ElementPresence(BaseModel):
    """
    Evaluation of a single required element's presence in an image.

    Examples:
    - element: "steam locomotive", present: true, details: "Large steam locomotive clearly visible in center of image"
    - element: "tropical beach", present: false, details: "Beach is present but lacks tropical features"
    """
    element: str
    present: bool
    details: str

class ObjectiveCriteriaResponse(BaseModel):
    """
    A structured evaluation of an image against its required elements.
    """
    required_elements: List[ElementPresence]
    composition_issues: List[str]
    technical_issues: List[str]
    style_match: bool
    overall_score: float
    evaluation_notes: str

class PromptElements(BaseModel):
    """
    A model for breaking down image generation prompts into required visual elements.

    Examples:
    - "A steam locomotive in the snow": ["steam locomotive", "snow environment", "visible steam/smoke"]
    - "A red cat sleeping on a blue couch": ["red cat", "blue couch", "sleeping pose"]
    - "A sunset over a tropical beach with palm trees": ["sunset sky", "tropical beach", "palm trees"]
    """
    chain_of_thought: str = Field(
        ...,
        description="The reasoning process for breaking down the prompt into elements"
    )
    required_elements: List[str] = Field(
        ...,
        description="The list of distinct visual elements that must be present in the image"
    )

class ObjectiveRatingRequest(BaseModel):
    image_data: str
    prompt: str


class EvaluationRequest(BaseModel):
    """Request model for running an evaluation batch"""

    description: Optional[str] = None
    num_iterations: int = 5  # Number of iterations per prompt
    custom_prompts: Optional[List[str]] = None  # Optional custom prompts to evaluate


class EvaluationResult(BaseModel):
    """Individual evaluation result"""
    prompt: str
    prompt_id: str
    image_data: str
    similarity_score: float
    objective_evaluation: ObjectiveCriteriaResponse
    feedback: str


class BatchMetrics(BaseModel):
    """Aggregate metrics for a batch"""
    avg_similarity_score: float
    avg_objective_score: float
    technical_issues_frequency: dict[str, int] = Field(default_factory=dict)


class EvaluationResponse(BaseModel):
    """Complete response for an evaluation batch"""

    batch_id: str
    description: Optional[str]
    timestamp: str
    prompts: Optional[List[str]]
    metrics: BatchMetrics
    results: List[EvaluationResult]


class ImageGenerationRequest(BaseModel):
    prompt: str


class ImageDescriptionRequest(BaseModel):
    image_data: str


class ImageSimilarityRequest(BaseModel):
    prompt: str
    image_data: str


class TextToSpeechRequest(BaseModel):
    text: str

class TechnicalIssueCategory(str, Enum):
    CLARITY = "Image Clarity"
    COMPOSITION = "Composition"
    COLOR = "Color Issues"
    ARTIFACTS = "Digital Artifacts"
    ANATOMY = "Anatomical Issues"
    RENDERING = "Rendering Problems"
    OTHER = "Other Issues"

# Mapping of keywords/phrases to categories
ISSUE_CATEGORY_MAPPING = {
    # Clarity issues
    "blur": TechnicalIssueCategory.CLARITY,
    "blurry": TechnicalIssueCategory.CLARITY,
    "focus": TechnicalIssueCategory.CLARITY,
    "sharp": TechnicalIssueCategory.CLARITY,
    "noise": TechnicalIssueCategory.CLARITY,
    "pixelation": TechnicalIssueCategory.CLARITY,

    # Composition issues
    "composition": TechnicalIssueCategory.COMPOSITION,
    "framing": TechnicalIssueCategory.COMPOSITION,
    "cropping": TechnicalIssueCategory.COMPOSITION,
    "alignment": TechnicalIssueCategory.COMPOSITION,
    "balance": TechnicalIssueCategory.COMPOSITION,
    "spacing": TechnicalIssueCategory.COMPOSITION,

    # Color issues
    "color": TechnicalIssueCategory.COLOR,
    "chromatic": TechnicalIssueCategory.COLOR,
    "saturation": TechnicalIssueCategory.COLOR,
    "contrast": TechnicalIssueCategory.COLOR,
    "tone": TechnicalIssueCategory.COLOR,
    "lighting": TechnicalIssueCategory.COLOR,

    # Digital artifacts
    "artifact": TechnicalIssueCategory.ARTIFACTS,
    "glitch": TechnicalIssueCategory.ARTIFACTS,
    "distortion": TechnicalIssueCategory.ARTIFACTS,
    "corruption": TechnicalIssueCategory.ARTIFACTS,

    # Anatomical issues
    "anatomy": TechnicalIssueCategory.ANATOMY,
    "proportion": TechnicalIssueCategory.ANATOMY,
    "anatomical": TechnicalIssueCategory.ANATOMY,
    "body": TechnicalIssueCategory.ANATOMY,

    # Rendering issues
    "rendering": TechnicalIssueCategory.RENDERING,
    "texture": TechnicalIssueCategory.RENDERING,
    "surface": TechnicalIssueCategory.RENDERING,
    "detail": TechnicalIssueCategory.RENDERING,
}
