import firebase_admin
from firebase_admin import credentials, storage
import os
import base64
import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List

# Load the base64 encoded Firebase service account key from environment
firebase_service_account_base64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")

if firebase_service_account_base64 is None:
    raise Exception("Firebase service account key is not found in environment variables.")

# Decode the base64 string to get the original JSON key
firebase_service_account_json = base64.b64decode(firebase_service_account_base64).decode('utf-8')

# Convert the JSON string into a dictionary
firebase_credentials = json.loads(firebase_service_account_json)

# Initialize Firebase Admin SDK using the decoded credentials
firebase_admin.initialize_app(credentials.Certificate(firebase_credentials), {'storageBucket': 'neurolabs-apk-download.appspot.com'})

# MongoDB Connection Setup
client = AsyncIOMotorClient('mongodb+srv://neurolabsinnovationsdocs:Neurolabs%40123@cluster0.elyma.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client["Application_DB"]
admin_collection = db["App_data"]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload/")
async def upload_files(
    apk: UploadFile = File(None),  # APK is optional
    ipa: UploadFile = File(...),  # IPA is now required
    images: List[UploadFile] = File(...),  # Images are required
):
    directories = {
        "apk": "APP",
        "ipa": "IOS",
        "images": "IMAGES"
    }

    if not ipa:
        raise HTTPException(status_code=400, detail="IPA file is required.")

    try:
        # Firebase Storage bucket reference
        bucket = storage.bucket()

        # Upload APK file if provided
        if apk and apk.filename.endswith(".apk"):
            apk_blob = bucket.blob(f'{directories["apk"]}/{apk.filename}')
            apk_blob.upload_from_file(apk.file, content_type=apk.content_type)
            apk_blob.make_public()
            apk_url = apk_blob.public_url
        else:
            apk_url = None

        # Upload IPA file
        if ipa.filename.endswith(".ipa"):
            ipa_blob = bucket.blob(f'{directories["ipa"]}/{ipa.filename}')
            ipa_blob.upload_from_file(ipa.file, content_type=ipa.content_type)
            ipa_blob.make_public()
            ipa_url = ipa_blob.public_url
        else:
            raise HTTPException(status_code=400, detail="Only IPA files are allowed for the IPA input.")

        # Upload image files (multiple images)
        image_urls = []
        for image in images:
            if image.content_type.startswith("image/"):
                image_blob = bucket.blob(f'{directories["images"]}/{image.filename}')
                image_blob.upload_from_file(image.file, content_type=image.content_type)
                image_blob.make_public()
                image_urls.append(image_blob.public_url)
            else:
                raise HTTPException(status_code=400, detail="Only image files are allowed for the Images input.")

        # Store the file URLs in MongoDB
        file_data = {
            "apk_url": apk_url,
            "ipa_url": ipa_url,
            "image_urls": image_urls
        }

        # Insert the file metadata into MongoDB
        await admin_collection.insert_one(file_data)

        # Return response with file URLs
        return JSONResponse(content={
            "message": "Files uploaded successfully",
            "apk_url": apk_url,
            "ipa_url": ipa_url,
            "image_urls": image_urls
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/files/")
async def list_files():
    try:
        # Fetch all file URLs from MongoDB
        files = await admin_collection.find({}).to_list(length=100)  # Adjust the length based on your requirements

        if not files:
            raise HTTPException(status_code=404, detail="No files found")

        # Prepare the response data in the format that frontend expects
        file_data = []
        for file in files:
            file_info = {
                "apk_url": file.get("apk_url", "not available"),
                "ipa_url": file.get("ipa_url", "not available"),
                "image_urls": file.get("image_urls", [])
            }
            file_data.append(file_info)

        return JSONResponse(content={
            "message": "Files fetched successfully",
            "files": file_data
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching files: {str(e)}")

@app.get("/")
def index():
    return {"Message": "APK Downloader"}
