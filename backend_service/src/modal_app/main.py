import asyncio
import base64
import json
import os
import sqlite3
import uuid
from datetime import datetime
from io import BytesIO
from urllib.request import urlopen

import instructor
from fastapi import File, HTTPException, UploadFile
from modal import asgi_app
from openai import OpenAI, AsyncOpenAI
from PIL import Image
from sentence_transformers import SentenceTransformer, util

from .common import DB_PATH, VOLUME_DIR, app, fastapi_app, volume
from .utils import break_down_prompt, aggregate_issues_by_category, get_or_create_prompt_ids, write_results_to_db, calculate_metrics
from .models import (
    BatchMetrics,
    EvaluationRequest,
    EvaluationResponse,
    EvaluationResult,
    ImageDescriptionRequest,
    ImageGenerationRequest,
    ImageSimilarityRequest,
    ObjectiveRatingRequest,
    ObjectiveCriteriaResponse,
    TextToSpeechRequest,
)

DEFAULT_TEST_PROMPTS = [
    "A Steam Locomotive in the snow",
    "A Painting of a peacock perched in a golden archway",
    "An Underwater Scene of an Ancient Temple Complex",
    "A Solitary Lighthouse on a Rocky Cliff",
    "A Macro Photograph of a Mechanical Watch Movement",
]

DEFAULT_TEST_PROMPTS_V2 = [
    "Create a hyperrealistic photograph of a steam locomotive charging through a heavy snowstorm at night, with the headlight piercing through the darkness and steam billowing dramatically. The scene should have strong contrast between light and shadow, with ice formations visible on the front of the engine.",
    "Design an elaborate Art Nouveau-style illustration of a peacock perched in a golden archway, surrounded by ornate floral patterns incorporating lilies and roses. The peacock's tail should be fully displayed with intricate detail in jewel tones, and metallic architectural elements should frame the composition.",
    "Render a detailed underwater scene of an ancient temple complex discovered in a coral reef, with rays of sunlight filtering through crystal-clear water. Include schools of tropical fish, partially buried stone sculptures covered in coral, and sea plants growing between weathered stone columns.",
    "Compose a cinematic widescreen shot of a solitary lighthouse on a rocky cliff during a fierce storm at sunset. The lighthouse beam should cut through dark storm clouds, waves should be crashing against the rocks below, and there should be visible weather effects like rain and lightning in the background.",
    "Create a highly detailed macro photograph of a mechanical watch movement, focusing on the intricate gears, springs, and jewels. The image should have shallow depth of field, with some elements in sharp focus while others softly blur. Include subtle reflections on the polished metal surfaces.",
]


@app.function(
    volumes={VOLUME_DIR: volume},
)
def init_db():
    """Initialize the SQLite database with a simple table."""
    volume.reload()
    conn = sqlite3.connect(DB_PATH)
    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS evaluation_batches (
        batch_id TEXT PRIMARY KEY,
        timestamp DATETIME NOT NULL,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS test_prompts (
        prompt_id TEXT PRIMARY KEY,
        prompt_text TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS generated_images (
        image_id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL,
        prompt_id TEXT NOT NULL,
        prompt_text TEXT NOT NULL,
        image_data TEXT NOT NULL,
        iteration INTEGER NOT NULL,
        similarity_score REAL,
        prompt_elements JSON,
        objective_evaluation JSON,
        llm_feedback TEXT,
        FOREIGN KEY (batch_id) REFERENCES evaluation_batches(batch_id),
        FOREIGN KEY (prompt_id) REFERENCES test_prompts(prompt_id)
    );

    CREATE TABLE IF NOT EXISTS batch_metrics (
        batch_id TEXT NOT NULL,
        avg_similarity_score REAL,
        avg_llm_score REAL,
        timestamp DATETIME NOT NULL,
        FOREIGN KEY (batch_id) REFERENCES evaluation_batches(batch_id)
    );
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    volume.commit()


async def url_to_base64(url: str) -> str:
    """Convert an image URL to a base64 encoded string."""
    try:
        response = urlopen(url)
        image_data = response.read()
        return base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        print(f"Error converting image to base64: {str(e)}")
        raise


@app.function(volumes={VOLUME_DIR: volume}, timeout=50000)
@asgi_app()
def fastapi_entrypoint():
    # Initialize database on startup
    init_db.remote()
    return fastapi_app



@fastapi_app.post("/evaluate", response_model=EvaluationResponse)
async def run_evaluation(request: EvaluationRequest):
    """Run a complete evaluation batch and return results"""
    try:
        batch_id = str(uuid.uuid4())
        timestamp = datetime.now()

        # Create batch record
        volume.reload()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO evaluation_batches (batch_id, timestamp, description) VALUES (?, ?, ?)",
                (batch_id, timestamp, request.description),
            )
            conn.commit()

        volume.commit()
        prompts = (
            request.custom_prompts if request.custom_prompts else DEFAULT_TEST_PROMPTS_V2
        )
        prompt_map = get_or_create_prompt_ids(conn, prompts)

        tasks = []
        for prompt in prompts:
            prompt_id = prompt_map[prompt]
            for iteration in range(request.num_iterations):
                task = process_single_iteration(
                    prompt, prompt_id, batch_id, iteration
                )
                tasks.append(task)

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = [r for r in raw_results if isinstance(r, EvaluationResult)]
        volume.reload()

        write_results_to_db(batch_id, valid_results)
        volume.commit()
        metrics = calculate_metrics(batch_id)

        return EvaluationResponse(
            batch_id=batch_id,
            description=request.description,
            timestamp=timestamp.isoformat(),
            prompts=prompts,
            metrics=metrics,
            results=valid_results,
        )

    except Exception as e:
        print(f"Evaluation failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Evaluation failed: {str(e)}"
        ) from e


@fastapi_app.get("/evaluation/{batch_id}", response_model=EvaluationResponse)
async def get_evaluation_results(batch_id: str):
    """Retrieve results for a specific evaluation batch"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Get batch info
            batch = conn.execute(
                """
                SELECT description, timestamp
                FROM evaluation_batches
                WHERE batch_id = ?
                """,
                (batch_id,)
            ).fetchone()

            if not batch:
                raise HTTPException(status_code=404, detail="Batch not found")

            # Get all evaluation results
            results = conn.execute(
                """
                SELECT
                    prompt_text,
                    image_data,
                    similarity_score,
                    objective_evaluation,
                    llm_feedback,
                    prompt_id
                FROM generated_images
                WHERE batch_id = ?
                ORDER BY prompt_text, iteration
                """,
                (batch_id,)
            ).fetchall()

            # Process results and collect technical issues
            evaluation_results = []
            all_issues = []

            for r in results:
                try:
                    objective_eval = json.loads(r[3]) if r[3] else None
                    if objective_eval and 'technical_issues' in objective_eval:
                        all_issues.extend(objective_eval['technical_issues'])

                    result = EvaluationResult(
                        prompt=r[0],
                        image_data=r[1],
                        similarity_score=r[2],
                        objective_evaluation=objective_eval,
                        feedback=r[4],
                        prompt_id=r[5]
                    )
                    evaluation_results.append(result)
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON for result: {e}")
                    continue

            # Calculate averages
            similarity_scores = [r.similarity_score for r in evaluation_results if r.similarity_score is not None]
            objective_scores = [r.objective_evaluation.overall_score for r in evaluation_results
                              if r.objective_evaluation and r.objective_evaluation.overall_score is not None]

            avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0
            avg_objective = sum(objective_scores) / len(objective_scores) if objective_scores else 0.0

            # Categorize and aggregate issues
            categorized_issues = aggregate_issues_by_category(all_issues)

            batch_metrics = BatchMetrics(
                avg_similarity_score=avg_similarity,
                avg_objective_score=avg_objective,
                technical_issues_frequency=categorized_issues
            )

            return EvaluationResponse(
                batch_id=batch_id,
                description=batch[0],
                timestamp=batch[1],
                prompts=list(set(r.prompt for r in evaluation_results)),
                metrics=batch_metrics,
                results=evaluation_results
            )

    except sqlite3.Error as e:
        print(f"Database error in get_evaluation_results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        print(f"Unexpected error in get_evaluation_results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@fastapi_app.get("/evaluation_batches")
async def get_evaluation_batches():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            batches = conn.execute(
                """
                SELECT
                    eb.batch_id,
                    eb.description,
                    eb.timestamp,
                    COUNT(gi.image_id) as image_count
                FROM evaluation_batches eb
                LEFT JOIN generated_images gi ON eb.batch_id = gi.batch_id
                GROUP BY eb.batch_id
                ORDER BY eb.timestamp DESC
            """
            ).fetchall()

            return [
                {
                    "batch_id": batch[0],
                    "description": batch[1],
                    "timestamp": batch[2],
                    "image_count": batch[3],
                }
                for batch in batches
            ]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@fastapi_app.post("/rate_quality")
async def objective_evaluation(request: ObjectiveRatingRequest) -> ObjectiveCriteriaResponse:
    """Perform detailed objective evaluation of an image against its prompt."""
    # First, get the structured elements from the prompt
    elements = await break_down_prompt(request.prompt)

    client = instructor.apatch(AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]))

    try:
        return await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""Evaluate this image generated from: "{request.prompt}"

                            Required elements to verify:
                            {[elem for elem in elements.required_elements]}

                            For each element:
                            1. Is it present in the image?
                            2. Provide specific details about how well it matches

                            Also check for:
                            1. Technical issues (blur, distortion, anatomy, etc.)
                            2. Composition issues (balance, cropping, focal point)
                            3. Style consistency with prompt

                            Be specific and critical. Cite concrete examples.
                            Score overall quality from 0.0 to 1.0."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{request.image_data}"
                            }
                        }
                    ]
                }
            ],
            response_model=ObjectiveCriteriaResponse,
            max_tokens=1000
        )

    except Exception as e:
        print(f"Objective evaluation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@fastapi_app.post("/generate_image")
async def generate_image(request: ImageGenerationRequest):
    async_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        response = await async_client.images.generate(
            model="dall-e-2",
            prompt=request.prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_base64 = await url_to_base64(response.data[0].url)
        return {"image_data": image_base64}
    except Exception as e:
        print(f"Image generation error: {str(e)}")
        return {"error": str(e)}, 500


@fastapi_app.post("/text_to_speech")
async def text_to_speech(request: TextToSpeechRequest):
    # client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    async_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        response = await async_client.audio.speech.create(
            model="tts-1", voice="alloy", input=request.text
        )
        # Convert the binary response to base64 for easy transfer
        audio_base64 = base64.b64encode(response.content).decode("utf-8")
        return {"audio": audio_base64}
    except Exception as e:
        print(f"TTS error: {str(e)}")
        return {"error": str(e)}, 500


@fastapi_app.post("/analyze_image_similarity")
async def analyze_image_similarity(request: ImageSimilarityRequest):
    try:
        # Load CLIP model
        model = SentenceTransformer("clip-ViT-B-32")

        # Convert base64 to PIL Image
        image_data = base64.b64decode(request.image_data)

        image = Image.open(BytesIO(image_data)).convert("RGB")

        img_emb = model.encode(image)
        text_emb = model.encode([request.prompt])
        similarity = util.cos_sim(img_emb, text_emb)
        print(f"the similarity directly: {similarity}")
        similarity_score = float(similarity[0][0]) * 100  # Convert to percentage
        print(f"the similarity as a percentage: {similarity_score}")

        return {
            "similarity_score": similarity_score,
        }

    except Exception as e:
        print(f"Analysis error: {str(e)}")
        return {"error": str(e)}, 500


@fastapi_app.post("/describe")
async def describe_image(request: ImageDescriptionRequest):
    async_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    vision_response = await async_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please provide a detailed description of this image.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{request.image_data}"
                        },
                    },
                ],
            }
        ],
        max_tokens=300,
    )

    description = vision_response.choices[0].message.content
    return {"image_description": description}


@fastapi_app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    if not file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an audio file. Received: " + file.content_type,
        )
    try:
        audio_bytes = await file.read()
        audio_file = BytesIO(audio_bytes)
        audio_file.name = file.filename or "audio.webm"

        # Print some debug info
        print(f"Processing audio file: {file.filename}")
        print(f"Content type: {file.content_type}")
        print(f"File size: {len(audio_bytes)} bytes")

        transcription = client.audio.transcriptions.create(
            model="whisper-1", file=audio_file
        )
        return {"transcript": transcription.text}
    except Exception as e:
        print("there was an error")
        print(str(e))
        return {"error": str(e)}, 500


@fastapi_app.get("/")
def read_root():
    return {"message": "Hello World"}


async def process_single_iteration(
    prompt: str, prompt_id: str, batch_id: str, iteration: int
) -> EvaluationResult | None:
    """Process a single iteration of image generation and evaluation"""
    async with asyncio.Semaphore(25):
        try:
            # Generate image
            image_response = await generate_image(ImageGenerationRequest(prompt=prompt))
            image_data = image_response["image_data"]

            # Run all analysis tasks concurrently
            similarity_task = analyze_image_similarity(
                ImageSimilarityRequest(prompt=prompt, image_data=image_data)
            )


            objective_task = objective_evaluation(
                ObjectiveRatingRequest(prompt=prompt, image_data=image_data)
            )

            description_task = describe_image(
                ImageDescriptionRequest(image_data=image_data)
            )

            # Wait for all tasks to complete
            similarity_response, objective_response, description_response = (
                await asyncio.gather(similarity_task, objective_task, description_task)
            )

            # Create result object
            return EvaluationResult(
                prompt=prompt,
                prompt_id=prompt_id,
                image_data=image_data,
                similarity_score=similarity_response["similarity_score"],
                objective_evaluation=objective_response,
                feedback=description_response["image_description"],
            )

        except Exception as e:
            print(
                f"Error processing iteration {iteration} for prompt '{prompt}': {str(e)}"
            )
            return None
