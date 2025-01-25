import sqlite3
from io import BytesIO
from urllib.request import urlopen
import base64
import os

from modal import asgi_app
from PIL import Image
from fastapi import UploadFile, File, HTTPException
from openai import OpenAI
from sentence_transformers import SentenceTransformer, util

from .common import DB_PATH, VOLUME_DIR, app, fastapi_app, volume
from .models import ImageGenerationRequest, ImageSimilarityRequest, TextToSpeechRequest

@app.function(
    volumes={VOLUME_DIR: volume},
)
def init_db():
    """Initialize the SQLite database with a simple table."""
    volume.reload()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Create a simple table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.commit()
    conn.close()
    volume.commit()

@app.function(
    volumes={VOLUME_DIR: volume},
)
@asgi_app()
def fastapi_entrypoint():
    # Initialize database on startup
    init_db.remote()
    return fastapi_app

@fastapi_app.post("/items/{name}")
async def create_item(name: str):
    volume.reload()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO items (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()
    volume.commit()
    return {"message": f"Added item: {name}"}

@fastapi_app.get("/items")
async def list_items():
    volume.reload()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()
    conn.close()
    return {
        "items": [
            {"id": item[0], "name": item[1], "created_at": item[2]} for item in items
        ]
    }

@fastapi_app.get("/")
def read_root():
    return {"message": "Hello World"}

@fastapi_app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    client = OpenAI()
    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=file
    )
    return {"transcript": transcription.text}

@fastapi_app.post("/generate_image")
async def generate_image(request: ImageGenerationRequest):
    client = OpenAI()
    response = client.images.generate(
        model="dall-e-3",
        prompt=request.prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    return {"image_url": response.data[0].url}

@fastapi_app.post("/analyze_image_similarity")
async def analyze_image_similarity(request: ImageSimilarityRequest):
    # CLIP for numerical similarity
    model = SentenceTransformer('clip-ViT-B-32')
    # massage the image into the format the model wants
    image_response = urlopen(request.image_url)
    image = Image.open(BytesIO(image_response.read())).convert('RGB')
    # get the image and text embeddings
    img_emb = model.encode(image)
    text_emb = model.encode([request.prompt])
    # get the similarity between the image and text embeddings
    similarity = util.cos_sim(img_emb, text_emb)
    
    # Vision model for detailed analysis
    client = OpenAI()
    vision_response = client.chat.completions.create(
        model="gpt-4-vision-preview",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image."},
                {"type": "image_url", "image_url": {"url": request.image_url}}
            ]
        }]
    )
    return {
        "similarity_score": float(similarity[0][0]) * 100,
        "image_description": vision_response.choices[0].message.content
    }

@fastapi_app.post("/text_to_speech")
async def text_to_speech(request: TextToSpeechRequest):
    client = OpenAI()
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=request.text
    )
    audio_base64 = base64.b64encode(response.content).decode('utf-8')
    return {"audio": audio_base64}