import uuid
import json
from openai import AsyncOpenAI
import instructor
import os
import sqlite3
from typing import Dict, List
from fastapi import HTTPException

from .models import PromptElements, EvaluationResult, TechnicalIssueCategory, ISSUE_CATEGORY_MAPPING, BatchMetrics
from .common import DB_PATH



def categorize_issue(issue: str) -> TechnicalIssueCategory:
    """Categorize a technical issue based on its description."""
    issue_lower = issue.lower()

    # Check each keyword in the mapping
    for keyword, category in ISSUE_CATEGORY_MAPPING.items():
        if keyword in issue_lower:
            return category

    # If no matching keywords found, return OTHER
    return TechnicalIssueCategory.OTHER

def aggregate_issues_by_category(issues: List[str]) -> Dict[str, int]:
    """Convert a list of specific issues into categorized counts."""
    category_counts = {}

    for issue in issues:
        category = categorize_issue(issue)
        category_counts[category] = category_counts.get(category, 0) + 1

    return category_counts

def get_or_create_prompt_ids(conn, prompts):
    """
    Get existing prompt IDs or create new ones for the given prompts.
    Returns a dictionary mapping prompt text to prompt IDs.
    """
    prompt_map = {}

    for prompt in prompts:
        # First, try to find an existing prompt
        cursor = conn.execute(
            "SELECT prompt_id FROM test_prompts WHERE prompt_text = ?", (prompt,)
        )
        result = cursor.fetchone()

        if result:
            # If prompt exists, use its ID
            prompt_map[prompt] = result[0]
        else:
            # If prompt doesn't exist, create new ID and insert
            new_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO test_prompts (prompt_id, prompt_text) VALUES (?, ?)",
                (new_id, prompt),
            )
            conn.commit()
            prompt_map[prompt] = new_id

    conn.close()
    return prompt_map



async def break_down_prompt(prompt: str) -> PromptElements:
    """Extract key visual elements from an image generation prompt."""
    client = instructor.apatch(AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]))

    return await client.chat.completions.create(
        model="gpt-4o",
        response_model=PromptElements,
        messages=[
            {
                "role": "user",
                "content": f"""Break down this image generation prompt into its essential visual elements: "{prompt}"

                Rules:
                1. Each element should be a distinct, assessable visual component
                2. Include specific attributes (colors, materials, etc.)
                3. Include environmental or contextual elements
                4. Include important spatial relationships
                5. Break complex objects into key parts if needed

                The elements should be specific enough that each one can be clearly verified as present or absent in an image."""
            }
        ],
        temperature=0.0
    )

def write_results_to_db(batch_id: str, results: List[EvaluationResult]):
    """Write all results to the database sequentially."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "PRAGMA journal_mode=WAL;"
            )  # Enable better concurrency handling
            for result in results:
                conn.execute(
                    """
                    INSERT INTO generated_images
                    (image_id, batch_id, prompt_id, prompt_text, image_data, iteration,
                        similarity_score, objective_evaluation, llm_feedback)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        batch_id,
                        result.prompt_id,
                        result.prompt,
                        result.image_data,
                        0,  # Replace with the iteration index if you have it
                        result.similarity_score,
                        json.dumps(result.objective_evaluation.dict()),
                        result.feedback,
                    ),
                )
                conn.commit()
    except Exception as e:
        print(f"Database write error: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to write results to database"
        )



def calculate_metrics(batch_id: str) -> BatchMetrics:
    """Calculate and return batch metrics from the database."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            cursor = conn.execute(
                """
                SELECT
                    AVG(similarity_score) as avg_similarity,
                    AVG(CAST(json_extract(objective_evaluation, '$.overall_score') AS FLOAT)) as avg_objective_score
                FROM generated_images
                WHERE batch_id = ?
                """,
                (batch_id,),
            )
            row = cursor.fetchone()
            avg_similarity = row["avg_similarity"] or 0.0
            avg_objective = row["avg_objective_score"] or 0.0

            # Extract technical issues distribution
            cursor = conn.execute(
                """
                SELECT objective_evaluation
                FROM generated_images
                WHERE batch_id = ? AND objective_evaluation IS NOT NULL
                """,
                (batch_id,)
            )
            issue_counts = {}
            for row in cursor:
                try:
                    eval_data = json.loads(row["objective_evaluation"])
                    if "technical_issues" in eval_data and isinstance(eval_data["technical_issues"], list):
                        for issue in eval_data["technical_issues"]:
                            # Normalize issue text to prevent duplicate categories
                            normalized_issue = issue.strip().lower()
                            issue_counts[normalized_issue] = issue_counts.get(normalized_issue, 0) + 1
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Error processing technical issues: {e}")
                    continue

        return BatchMetrics(
            avg_similarity_score=avg_similarity,
            avg_objective_score=avg_objective,
            technical_issues_frequency=issue_counts
        )
    except Exception as e:
        print(f"Metric calculation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to calculate metrics")
